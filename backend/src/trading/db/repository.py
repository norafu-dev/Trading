"""在同一事务内保存消息当前内容和快照版本，处理重复投递与乱序版本。"""

from datetime import UTC, datetime

from sqlalchemy import desc, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from trading.collector.messages import MessageSnapshot
from trading.db.media import enqueue_images
from trading.db.models import Message, MessageVersion


async def latest_message_id(engine: AsyncEngine, channel_id: str) -> str | None:
    """读取指定频道最后保存的消息 ID，供 Collector 从已知位置之后补采。"""
    async with engine.connect() as connection:
        return await connection.scalar(
            select(Message.message_id)
            .where(Message.channel_id == channel_id)
            .order_by(desc(Message.created_at), desc(Message.message_id))
            .limit(1)
        )


async def store_snapshot(engine: AsyncEngine, snapshot: MessageSnapshot) -> bool:
    """在同一事务中保存当前消息和版本。重复快照不新增版本，旧版本不覆盖新内容。"""
    now = datetime.now(UTC)
    payload = snapshot.model_dump(mode="json")
    statement = insert(Message).values(
        message_id=snapshot.message_id,
        channel_id=snapshot.channel_id,
        author_id=snapshot.author_id,
        content=snapshot.content,
        created_at=snapshot.created_at,
        version_at=snapshot.version_at,
        first_seen_at=now,
        last_seen_at=now,
        snapshot=payload,
    )
    statement = statement.on_conflict_do_update(
        index_elements=[Message.message_id],
        set_={
            "content": statement.excluded.content,
            "version_at": statement.excluded.version_at,
            "last_seen_at": func.greatest(Message.last_seen_at, statement.excluded.last_seen_at),
            "snapshot": statement.excluded.snapshot,
        },
        where=statement.excluded.version_at >= Message.version_at,
    )
    async with engine.begin() as connection:
        await connection.execute(statement)
        await enqueue_images(connection, payload)
        new_version = await connection.scalar(
            insert(MessageVersion)
            .values(
                message_id=snapshot.message_id,
                fingerprint=snapshot.fingerprint,
                version_at=snapshot.version_at,
                observed_at=now,
                snapshot=payload,
            )
            .on_conflict_do_nothing()
            .returning(MessageVersion.fingerprint)
        )
    return new_version is not None
