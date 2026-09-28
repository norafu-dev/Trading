"""处理 Discord 连接和消息回调，协调来源同步、心跳与幂等写入。"""

import asyncio
import contextlib
import logging
from datetime import UTC, datetime

# 安装包是 discord.py-self，官方导入名仍为 discord；不是普通 Bot 库 discord.py。
import discord
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from trading.collector.messages import normalize_message
from trading.collector.subscriptions import SourceSubscriptions
from trading.config import Sources
from trading.db.control import add_event, update_runtime
from trading.db.repository import latest_message_id, store_snapshot

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_SECONDS = 5
MESSAGE_WRITE_ATTEMPTS = 3
BACKFILL_MESSAGE_LIMIT = 1000


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
        self.backfill_lock = asyncio.Lock()
        self.monitor_task: asyncio.Task | None = None
        self.subscriptions = SourceSubscriptions(engine, self)

    async def sync_sources(self) -> None:
        """刷新可用来源并报告同步时间与加载数量，供管理面板查看。"""
        self.sources = await self.subscriptions.refresh()
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
        await self.backfill_sources()

    async def on_resumed(self) -> None:
        """会话恢复后重新校验来源，并补采短时断线期间的近期消息。"""
        self.connection_state = "connected"
        self.subscriptions.clear()
        await update_runtime(self.engine, state="connected", last_error=None)
        await add_event(self.engine, "Discord 会话已恢复，正在检查断线期间的近期消息")
        await self.sync_sources()
        await self.backfill_sources()

    async def on_disconnect(self) -> None:
        """报告会话断开并清零面板中的活跃来源数，等待客户端自动重连。"""
        self.connection_state = "disconnected"
        await update_runtime(self.engine, state="disconnected", active_sources=0)
        await add_event(self.engine, "Discord 连接断开，等待自动重连", "warning")

    async def backfill_sources(self) -> None:
        """按来源补采本地断点之后最多一千条近期消息，单个来源失败不停止实时监听。"""
        async with self.backfill_lock:
            saved_count = 0
            failed_count = 0
            # 先冻结全部频道断点，避免重连后的实时消息先入库而跳过更早的缺口。
            async with self.write_lock:
                last_ids = {
                    source.channel_id: await latest_message_id(self.engine, source.channel_id)
                    for source in self.sources.sources
                }
            for source in self.sources.sources:
                try:
                    channel = self.get_channel(int(source.channel_id)) or await self.fetch_channel(
                        int(source.channel_id)
                    )
                    if not isinstance(channel, (discord.TextChannel, discord.Thread)):
                        continue
                    last_id = last_ids[source.channel_id]
                    after = discord.Object(id=int(last_id)) if last_id else None
                    async for message in channel.history(
                        limit=BACKFILL_MESSAGE_LIMIT,
                        after=after,
                        oldest_first=False,
                    ):
                        if await self.store_matching_message(message):
                            saved_count += 1
                except (
                    discord.Forbidden,
                    discord.NotFound,
                    discord.HTTPException,
                    OSError,
                    TimeoutError,
                ):
                    failed_count += 1
                    logger.warning("message_backfill_failed channel_id=%s", source.channel_id)
                    await add_event(
                        self.engine,
                        f"来源 {source.channel_id} 的近期消息补采失败，将在下次连接后重试",
                        "warning",
                    )
            await add_event(
                self.engine,
                f"近期消息补采完成：新增 {saved_count} 条，失败来源 {failed_count} 个",
                "warning" if failed_count else "info",
            )

    async def on_message(self, message: discord.Message) -> None:
        """过滤消息后标准化并幂等入库；串行写入并在可恢复错误时有限重试。"""
        await self.store_matching_message(message)

    async def store_matching_message(self, message: discord.Message) -> bool:
        """保存命中当前来源规则的消息；返回是否新增版本，供实时监听和补采共用。"""
        if not self.sources.matches(str(message.channel.id), str(message.author.id)):
            return False
        snapshot = normalize_message(message)
        async with self.write_lock:
            for attempt in range(MESSAGE_WRITE_ATTEMPTS):
                try:
                    added = await store_snapshot(self.engine, snapshot)
                    await update_runtime(
                        self.engine,
                        last_message_at=datetime.now(UTC),
                        last_saved_at=datetime.now(UTC),
                    )
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
        """先取消独立心跳任务，再关闭 Discord 连接；避免等待当前任务自身。"""
        if self.monitor_task and self.monitor_task is not asyncio.current_task():
            self.monitor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.monitor_task
        await super().close()
