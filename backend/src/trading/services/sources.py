"""管理来源配置变更与审计事件的原子事务，并转换可识别的领域错误。"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from trading.db.sources import record_source_event, remove_source, write_source
from trading.schemas import SourceDetails, SourceInput


class SourceNotFound(Exception):
    pass


class DuplicateSource(Exception):
    pass


async def save_source(
    engine: AsyncEngine, body: SourceInput, source_id: str | None = None
) -> SourceDetails:
    """原子保存来源配置和审计事件；只把唯一约束冲突映射为重复来源错误。"""
    now = datetime.now(UTC)
    try:
        # Configuration and its audit event must commit or roll back together.
        async with engine.begin() as connection:
            source = await write_source(
                connection, body, source_id or str(uuid4()), now, is_new=source_id is None
            )
            if source is None:
                raise SourceNotFound
            await record_source_event(connection, "采集来源配置已更新，等待 Collector 同步", now)
            return source
    except IntegrityError as error:
        # Only PostgreSQL's unique violation represents a duplicate channel.
        if getattr(error.orig, "sqlstate", None) != "23505":
            raise
        raise DuplicateSource from None


async def delete_source(engine: AsyncEngine, source_id: str) -> None:
    """原子删除来源配置并记录事件，保留已经采集的所有消息。"""
    async with engine.begin() as connection:
        if not await remove_source(connection, source_id):
            raise SourceNotFound
        await record_source_event(connection, "采集来源已移除，历史消息保留", datetime.now(UTC))
