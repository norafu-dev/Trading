"""执行来源配置与审计事件 SQL；事务由调用它的 Service 控制。"""

from datetime import datetime

from sqlalchemy import delete, insert, update
from sqlalchemy.ext.asyncio import AsyncConnection

from trading.db.models import ChannelSource, CollectorEvent
from trading.schemas import SourceDetails, SourceInput


async def write_source(
    connection: AsyncConnection, body: SourceInput, source_id: str, now: datetime, *, is_new: bool
) -> SourceDetails | None:
    """创建或更新来源并重置校验状态；使用调用方事务，更新不存在记录时返回空。"""
    values = {
        **body.model_dump(mode="json"),
        "status": "pending",
        "last_error": None,
        "checked_at": None,
        "updated_at": now,
    }
    if is_new:
        values.update(id=source_id, created_at=now)
        statement = insert(ChannelSource)
    else:
        statement = update(ChannelSource).where(ChannelSource.id == source_id)
    result = await connection.execute(
        statement.values(**values).returning(*ChannelSource.__table__.columns)
    )
    row = result.mappings().first()
    return SourceDetails.model_validate(row) if row else None


async def remove_source(connection: AsyncConnection, source_id: str) -> bool:
    """删除来源配置并返回是否存在；不访问消息表，沿用调用方事务。"""
    deleted_id = await connection.scalar(
        delete(ChannelSource).where(ChannelSource.id == source_id).returning(ChannelSource.id)
    )
    return deleted_id is not None


async def record_source_event(connection: AsyncConnection, message: str, now: datetime) -> None:
    """在调用方事务内追加配置事件，保证事件和来源变更一起提交或回滚。"""
    await connection.execute(
        insert(CollectorEvent).values(level="info", message=message, occurred_at=now)
    )
