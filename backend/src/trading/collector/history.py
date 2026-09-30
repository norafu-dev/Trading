"""独立后台历史扫描；按持久断点分页补采，失败可重试，不阻塞实时 Gateway 回调。"""

import asyncio

import discord
from sqlalchemy.exc import SQLAlchemyError

from trading.db.checkpoints import (
    advance_scan,
    begin_scan,
    fail_scan,
    finish_scan,
    initialize_history_window,
)
from trading.db.control import add_event

HISTORY_PAGE_SIZE = 100


class HistoryRecovery:
    """当前单 Collector 使用一个扫描任务，实时消息和补采分别推进各自状态。"""

    def __init__(self, client):
        """复用已登录客户端及消息保存链路，不创建第二个 Discord 会话。"""
        self.client = client

    async def scan_channel(self, channel_id: str) -> None:
        """从旧到新读取一页，每条成功处理后推进断点，短页才视为目标范围读完。"""
        engine = self.client.engine
        scan = await begin_scan(engine, channel_id)
        if scan is None:
            return
        try:
            channel = self.client.get_channel(int(channel_id)) or await self.client.fetch_channel(
                int(channel_id)
            )
            if not isinstance(channel, (discord.TextChannel, discord.Thread)):
                raise TypeError("Unsupported history channel")
            if scan["cursor_id"] == "0":
                # 只在首次启用保留原有最近千条范围，不能让频道全部历史挤压实时消息。
                recent = [
                    message
                    async for message in channel.history(
                        limit=1000,
                        before=discord.Object(id=int(scan["target_id"])),
                        oldest_first=False,
                    )
                ]
                earliest = min(recent, key=lambda message: message.id) if recent else None
                scan["cursor_id"] = str(earliest.id - 1) if earliest else scan["target_id"]
                await initialize_history_window(
                    engine,
                    channel_id,
                    scan["cursor_id"],
                    earliest.created_at if earliest else scan["coverage_started_at"],
                )
            count = 0
            async for message in channel.history(
                limit=HISTORY_PAGE_SIZE,
                after=discord.Object(id=int(scan["cursor_id"])),
                before=discord.Object(id=int(scan["target_id"])),
                oldest_first=True,
            ):
                await self.client.store_matching_message(message, "backfill")
                await advance_scan(engine, channel_id, str(message.id))
                count += 1
            await finish_scan(engine, channel_id, scan["target_id"], count < HISTORY_PAGE_SIZE)
            if scan["last_error"]:
                await add_event(engine, f"频道 {channel_id} 的历史补采已恢复")
        except (discord.HTTPException, OSError, TimeoutError, SQLAlchemyError, TypeError) as error:
            await fail_scan(engine, channel_id, type(error).__name__)
            if not scan["last_error"]:
                await add_event(
                    engine, f"频道 {channel_id} 的历史补采失败，已安排自动重试", "warning"
                )

    async def run(self) -> None:
        """轮流扫描有效频道，持续处理积压页；数据库故障交给 Collector 退出并重启。"""
        try:
            while not self.client.is_closed():
                if self.client.is_ready():
                    for source in list(self.client.sources.sources):
                        await self.scan_channel(source.channel_id)
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            raise
        except Exception:
            await self.client.on_error("history_recovery")
