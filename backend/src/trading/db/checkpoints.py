"""持久化历史扫描进度与重试状态；扫描断点从不由实时消息更新。"""

from datetime import UTC, datetime, timedelta

import discord
from sqlalchemy import Numeric, cast, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from trading.db.models import ChannelCheckpoint, ChannelSource, Message


async def ensure_checkpoint(engine: AsyncEngine, channel_id: str) -> None:
    """旧频道从最早已存消息前开始复核，新来源由后台建立最近千条的覆盖边界。"""
    async with engine.begin() as connection:
        if await connection.scalar(
            select(ChannelCheckpoint.channel_id).where(ChannelCheckpoint.channel_id == channel_id)
        ):
            return
        earliest = (
            await connection.execute(
                select(Message.message_id, Message.created_at)
                .where(Message.channel_id == channel_id)
                .order_by(cast(Message.message_id, Numeric))
                .limit(1)
            )
        ).first()
        configured_at = await connection.scalar(
            select(ChannelSource.created_at).where(ChannelSource.channel_id == channel_id)
        )
        started = earliest.created_at if earliest else configured_at or datetime.now(UTC)
        cursor = str(int(earliest.message_id) - 1) if earliest else "0"
        await connection.execute(
            insert(ChannelCheckpoint)
            .values(
                channel_id=channel_id,
                cursor_id=cursor,
                coverage_started_at=started,
                state="pending",
                attempts=0,
                next_attempt_at=datetime.now(UTC),
            )
            .on_conflict_do_nothing()
        )


async def initialize_history_window(
    engine: AsyncEngine, channel_id: str, cursor_id: str, started_at: datetime
) -> None:
    """新来源只初始化最近千条的起点，之后的断线补采不再受千条上限限制。"""
    async with engine.begin() as connection:
        await connection.execute(
            update(ChannelCheckpoint)
            .where(
                ChannelCheckpoint.channel_id == channel_id,
                ChannelCheckpoint.cursor_id == "0",
            )
            .values(cursor_id=cursor_id, coverage_started_at=started_at)
        )


async def begin_scan(engine: AsyncEngine, channel_id: str) -> dict | None:
    """到期后建立固定目标；失败重启继续原目标，不追随新实时消息跳过缺口。"""
    now = datetime.now(UTC)
    async with engine.begin() as connection:
        row = (
            (
                await connection.execute(
                    select(ChannelCheckpoint.__table__)
                    .where(
                        ChannelCheckpoint.channel_id == channel_id,
                        ChannelCheckpoint.next_attempt_at <= now,
                    )
                    .with_for_update()
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        target = row["target_id"] or str(discord.utils.time_snowflake(now, high=True))
        if int(target) <= int(row["cursor_id"]):
            return None
        await connection.execute(
            update(ChannelCheckpoint)
            .where(ChannelCheckpoint.channel_id == channel_id)
            .values(target_id=target, state="running")
        )
        return {**row, "target_id": target}


async def advance_scan(engine: AsyncEngine, channel_id: str, message_id: str) -> None:
    """消息保存或过滤成功后才推进扫描断点；重复扫描不能让游标倒退。"""
    async with engine.begin() as connection:
        await connection.execute(
            update(ChannelCheckpoint)
            .where(
                ChannelCheckpoint.channel_id == channel_id,
                cast(ChannelCheckpoint.cursor_id, Numeric) < int(message_id),
            )
            .values(cursor_id=message_id)
        )


async def finish_scan(engine: AsyncEngine, channel_id: str, target_id: str, complete: bool) -> None:
    """未读完的一页继续排队；扫描穷尽才推进目标并记为完成，之后定期核查新消息。"""
    now = datetime.now(UTC)
    values = dict(state="pending", attempts=0, last_error=None, next_attempt_at=now)
    if complete:
        values.update(
            cursor_id=target_id,
            target_id=None,
            state="idle",
            last_completed_at=now,
            next_attempt_at=now + timedelta(seconds=30),
        )
    async with engine.begin() as connection:
        await connection.execute(
            update(ChannelCheckpoint)
            .where(ChannelCheckpoint.channel_id == channel_id)
            .values(**values)
        )


async def fail_scan(engine: AsyncEngine, channel_id: str, error_type: str) -> None:
    """无限次数有限退避，保留已扫描游标与目标；记录类别而不输出原始异常或凭证。"""
    now = datetime.now(UTC)
    async with engine.begin() as connection:
        attempts = await connection.scalar(
            select(ChannelCheckpoint.attempts).where(ChannelCheckpoint.channel_id == channel_id)
        )
        attempts = (attempts or 0) + 1
        delay = min(5 * 2 ** min(attempts - 1, 6), 300)
        await connection.execute(
            update(ChannelCheckpoint)
            .where(ChannelCheckpoint.channel_id == channel_id)
            .values(
                state="error",
                attempts=attempts,
                next_attempt_at=now + timedelta(seconds=delay),
                last_error=f"历史补采失败（{error_type}），{delay} 秒后重试",
            )
        )


async def checkpoint_summary(engine: AsyncEngine) -> list[dict]:
    """返回仍配置的来源补采状态，删除来源不删除历史进度。"""
    async with engine.connect() as connection:
        return [
            dict(row)
            for row in (
                await connection.execute(
                    select(
                        ChannelCheckpoint.__table__,
                        ChannelSource.name,
                    )
                    .join(ChannelSource, ChannelSource.channel_id == ChannelCheckpoint.channel_id)
                    .order_by(ChannelSource.position, ChannelSource.name)
                )
            ).mappings()
        ]
