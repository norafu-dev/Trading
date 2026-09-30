"""处理 Discord 连接和消息回调，协调来源同步、心跳与幂等写入。"""

import asyncio
import contextlib
import logging
from datetime import UTC, datetime

# 安装包是 discord.py-self，官方导入名仍为 discord；不是普通 Bot 库 discord.py。
import discord
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from trading.collector.history import HistoryRecovery
from trading.collector.messages import MessageSnapshot, normalize_message
from trading.collector.subscriptions import SourceSubscriptions
from trading.config import Sources
from trading.db.checkpoints import ensure_checkpoint
from trading.db.control import add_event, update_runtime
from trading.db.repository import mark_deleted, store_snapshot, stored_snapshot

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_SECONDS = 5
MESSAGE_WRITE_ATTEMPTS = 3


class Collector(discord.Client):
    """继承 discord.py-self 的用户账号客户端，通过 Gateway 回调接收消息。"""

    def __init__(self, engine: AsyncEngine, sources: Sources | None = None) -> None:
        """初始化 Discord 客户端、来源规则、写入锁和后台任务状态。"""
        super().__init__(guild_subscriptions=False, chunk_guilds_at_startup=False)
        self.engine = engine
        self.sources = sources or Sources()
        self.failed = False
        self.connection_state = "connecting"
        self.write_lock = asyncio.Lock()
        self.monitor_task: asyncio.Task | None = None
        self.media_task: asyncio.Task | None = None
        self.history_task: asyncio.Task | None = None
        self.recovery = HistoryRecovery(self)
        self.subscriptions = SourceSubscriptions(engine, self)

    async def sync_sources(self) -> None:
        """刷新可用来源并报告同步时间与加载数量，供管理面板查看。"""
        sources = await self.subscriptions.refresh()
        for source in sources.sources:
            await ensure_checkpoint(self.engine, source.channel_id)
        self.sources = sources
        await update_runtime(
            self.engine, source_sync_at=datetime.now(UTC), active_sources=len(self.sources.sources)
        )

    async def monitor(self) -> None:
        """定期报告心跳；Discord 就绪时刷新来源，未处理异常使 Collector 停止。"""
        try:
            while not self.is_closed():
                await update_runtime(
                    self.engine, heartbeat_at=datetime.now(UTC), state=self.connection_state
                )
                if self.is_ready():
                    await self.sync_sources()
                await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception:
            await self.on_error("monitor")

    async def on_ready(self) -> None:
        """连接成功后同步来源，并补采每个来源在本地断点之后的近期消息。"""
        self.connection_state = "connected"
        self.subscriptions.clear()
        await update_runtime(
            self.engine, state="connected", connected_at=datetime.now(UTC), last_error=None
        )
        await add_event(self.engine, "Discord 已连接，正在同步来源并补采近期消息")
        await self.sync_sources()

    async def on_resumed(self) -> None:
        """会话恢复后重新校验来源，并补采短时断线期间的近期消息。"""
        self.connection_state = "connected"
        self.subscriptions.clear()
        await update_runtime(self.engine, state="connected", last_error=None)
        await add_event(self.engine, "Discord 会话已恢复，正在检查断线期间的近期消息")
        await self.sync_sources()

    async def on_disconnect(self) -> None:
        """报告会话断开并清零面板中的活跃来源数，等待客户端自动重连。"""
        self.connection_state = "disconnected"
        await update_runtime(self.engine, state="disconnected", active_sources=0)
        await add_event(self.engine, "Discord 连接断开，等待自动重连", "warning")

    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent) -> None:
        """处理无缓存或只有部分字段的编辑；合并原快照，未见过的消息读取完整内容。"""
        channel_id, message_id = str(payload.channel_id), str(payload.message_id)
        if not any(source.channel_id == channel_id for source in self.sources.sources):
            return
        async with self.write_lock:
            original = await stored_snapshot(self.engine, channel_id, message_id)
            if original and self.sources.matches(channel_id, original.author_id):
                data = original.model_dump(mode="json")
                for key in ("content", "attachments", "embeds"):
                    if key in payload.data:
                        data[key] = payload.data[key]
                if payload.data.get("edited_timestamp"):
                    data["edited_at"] = payload.data["edited_timestamp"]
                added = await store_snapshot(
                    self.engine, MessageSnapshot.model_validate(data), "edit"
                )
                now = datetime.now(UTC)
                await update_runtime(
                    self.engine, last_message_at=now, **({"last_saved_at": now} if added else {})
                )
                return
            if original:
                return
        # 未缓存且尚未入库时无法只凭局部事件重建原文，读取原消息并继续作者过滤。
        try:
            channel = self.get_channel(int(channel_id)) or await self.fetch_channel(int(channel_id))
            message = await channel.fetch_message(int(message_id))
            await self.store_matching_message(message, "edit")
        except discord.NotFound:
            await self.record_deletions(channel_id, [message_id])
        except (discord.HTTPException, OSError, TimeoutError):
            await add_event(
                self.engine, f"频道 {channel_id} 的消息编辑读取失败，原有记录保留", "warning"
            )

    async def record_deletions(self, channel_id: str, message_ids: list[str]) -> None:
        """只标记当前监听频道，串行保存墓碑，避免删除与旧快照写入竞态。"""
        if not any(source.channel_id == channel_id for source in self.sources.sources):
            return
        async with self.write_lock:
            await mark_deleted(self.engine, channel_id, message_ids)

    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        """单条删除不依赖缓存，保留已采集内容并记录删除时间。"""
        await self.record_deletions(str(payload.channel_id), [str(payload.message_id)])

    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent) -> None:
        """批量删除与单条删除共用墓碑规则，不清除历史版本或 R2 图片。"""
        await self.record_deletions(
            str(payload.channel_id), [str(value) for value in payload.message_ids]
        )

    async def on_message(self, message: discord.Message) -> None:
        """过滤消息后标准化并幂等入库；串行写入并在可恢复错误时有限重试。"""
        await self.store_matching_message(message)

    async def store_matching_message(
        self, message: discord.Message, observation_source: str = "realtime"
    ) -> bool:
        """保存命中当前来源规则的消息；返回是否新增版本，供实时监听和补采共用。"""
        if not self.sources.matches(str(message.channel.id), str(message.author.id)):
            return False
        snapshot = normalize_message(message)
        async with self.write_lock:
            for attempt in range(MESSAGE_WRITE_ATTEMPTS):
                try:
                    added = await store_snapshot(self.engine, snapshot, observation_source)
                    now = datetime.now(UTC)
                    runtime_changes = {"last_saved_at": now} if added else {}
                    if observation_source in {"realtime", "edit"}:
                        runtime_changes["last_message_at"] = now
                    if runtime_changes:
                        await update_runtime(self.engine, **runtime_changes)
                    logger.info("message_saved id=%s new_version=%s", snapshot.message_id, added)
                    return added
                except (SQLAlchemyError, OSError, TimeoutError) as error:
                    logger.warning(
                        "message_write_retry id=%s error_type=%s",
                        snapshot.message_id,
                        type(error).__name__,
                    )
                    if attempt == MESSAGE_WRITE_ATTEMPTS - 1:
                        raise
                    await asyncio.sleep(2**attempt)
        return False

    async def on_error(self, event_method: str, *args: object, **kwargs: object) -> None:
        """将回调故障标记为不可继续采集；尽力记录脱敏错误后关闭客户端。"""
        self.failed = True
        self.connection_state = "error"
        logger.error("collector_failed event=%s", event_method)
        # If the DB is unavailable, heartbeat expiry still marks the process stale.
        if self.engine is not None:
            with contextlib.suppress(SQLAlchemyError, OSError, TimeoutError):
                await update_runtime(
                    self.engine,
                    state="error",
                    active_sources=0,
                    last_error=f"Collector 处理失败（{event_method}），请检查服务日志",
                )
                await add_event(self.engine, f"Collector 已停止（{event_method}）", "error")
        await self.close()

    async def close(self) -> None:
        """先取消心跳、补采和图片归档任务，再关闭 Discord 连接；避免等待当前任务自身。"""
        if self.monitor_task and self.monitor_task is not asyncio.current_task():
            self.monitor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.monitor_task
        if self.history_task and self.history_task is not asyncio.current_task():
            self.history_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.history_task
        if self.media_task and self.media_task is not asyncio.current_task():
            self.media_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.media_task
        await super().close()
