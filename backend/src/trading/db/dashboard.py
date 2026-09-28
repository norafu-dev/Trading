"""查询面板所需的来源、进程记录、消息计数与最近消息和事件。"""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from trading.db.models import ChannelSource, CollectorEvent, CollectorRuntime, Message
from trading.schemas import EventSummary, MessageSummary, RuntimeDetails, SourceDetails

RECENT_RECORD_LIMIT = 20


@dataclass(frozen=True)
class DashboardRecords:
    sources: list[SourceDetails]
    runtime: RuntimeDetails
    total_messages: int
    messages: list[MessageSummary]
    events: list[EventSummary]


async def read_dashboard(engine: AsyncEngine) -> DashboardRecords:
    """读取面板显示所需的数据，限制消息与事件条数；状态解释交给 Service。"""
    async with engine.connect() as connection:
        source_result = await connection.execute(
            select(ChannelSource.__table__).order_by(ChannelSource.created_at)
        )
        runtime_result = await connection.execute(
            select(CollectorRuntime.__table__).where(CollectorRuntime.id == "primary")
        )
        total_messages = await connection.scalar(select(func.count()).select_from(Message))
        message_result = await connection.execute(
            select(
                Message.message_id,
                Message.channel_id,
                Message.author_id,
                Message.content,
                Message.created_at,
                Message.first_seen_at,
            )
            .order_by(Message.first_seen_at.desc())
            .limit(RECENT_RECORD_LIMIT)
        )
        event_result = await connection.execute(
            select(CollectorEvent.__table__)
            .order_by(CollectorEvent.id.desc())
            .limit(RECENT_RECORD_LIMIT)
        )
    return DashboardRecords(
        sources=[SourceDetails.model_validate(row) for row in source_result.mappings()],
        runtime=RuntimeDetails.model_validate(runtime_result.mappings().one()),
        total_messages=total_messages or 0,
        messages=[MessageSummary.model_validate(row) for row in message_result.mappings()],
        events=[
            EventSummary.model_validate({**row, "id": str(row["id"])})
            for row in event_result.mappings()
        ],
    )
