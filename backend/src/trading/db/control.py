"""读取启用来源，写入 Collector 心跳、运行事件和频道校验结果。"""

from datetime import UTC, datetime

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from trading.db.models import ChannelSource, CollectorEvent, CollectorRuntime
from trading.schemas import SourceDetails


async def enabled_sources(engine: AsyncEngine) -> list[SourceDetails]:
    """读取启用来源并转换为具名记录，供 Collector 进行频道校验。"""
    async with engine.connect() as connection:
        result = await connection.execute(
            select(ChannelSource.__table__).where(ChannelSource.enabled.is_(True))
        )
        return [SourceDetails.model_validate(row) for row in result.mappings()]


async def update_runtime(engine: AsyncEngine, **values) -> None:
    """在独立事务中更新主 Collector 的指定状态字段，不覆盖未传入字段。"""
    async with engine.begin() as connection:
        await connection.execute(
            update(CollectorRuntime).where(CollectorRuntime.id == "primary").values(**values)
        )


async def add_event(engine: AsyncEngine, message: str, level: str = "info") -> None:
    """在独立事务中追加运行事件；配置审计使用与配置同事务的专用写入函数。"""
    async with engine.begin() as connection:
        await connection.execute(
            insert(CollectorEvent).values(
                level=level, message=message, occurred_at=datetime.now(UTC)
            )
        )


async def mark_source(engine: AsyncEngine, source: SourceDetails, error: str | None) -> None:
    """仅更新仍启用且配置版本未改变的来源，避免旧校验结果覆盖用户的新配置。"""
    async with engine.begin() as connection:
        await connection.execute(
            update(ChannelSource)
            .where(
                ChannelSource.id == source.id,
                ChannelSource.updated_at == source.updated_at,
                ChannelSource.enabled.is_(True),
            )
            .values(
                status="error" if error else "ready",
                last_error=error,
                checked_at=datetime.now(UTC),
            )
        )
