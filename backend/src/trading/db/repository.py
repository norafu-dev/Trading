"""在同一事务内保存消息当前内容和快照版本，处理重复投递与乱序版本。"""

from datetime import UTC, datetime

from sqlalchemy import desc, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from trading.collector.messages import MessageSnapshot
from trading.db.media import enqueue_images
from trading.db.models import Message, MessageDeletion, MessageVersion


async def latest_message_id(engine: AsyncEngine, channel_id: str) -> str | None:
    """读取指定频道最后保存的消息 ID，供 Collector 从已知位置之后补采。"""
    async with engine.connect() as connection:
        return await connection.scalar(
            select(Message.message_id)
            .where(Message.channel_id == channel_id)
            .order_by(desc(Message.created_at), desc(Message.message_id))
            .limit(1)
        )


async def store_snapshot(
    engine: AsyncEngine, snapshot: MessageSnapshot, observation_source: str = "unknown"
) -> bool:
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
        first_delivery="backfill" if observation_source == "edit" else observation_source,
        deleted_at=select(MessageDeletion.observed_at)
        .where(
            MessageDeletion.message_id == snapshot.message_id,
            MessageDeletion.channel_id == snapshot.channel_id,
        )
        .scalar_subquery(),
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
        # 跨连接串行同一消息的保存与删除，防止墓碑先提交而并发快照仍读到旧视图。
        await connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:id, 0))"),
            {"id": snapshot.message_id},
        )
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
                observation_source=observation_source,
            )
            .on_conflict_do_nothing()
            .returning(MessageVersion.fingerprint)
        )
    return new_version is not None


async def stored_snapshot(
    engine: AsyncEngine, channel_id: str, message_id: str
) -> MessageSnapshot | None:
    """读取已留存快照，供原始编辑事件合并部分字段，不依赖 Discord 消息缓存。"""
    async with engine.connect() as connection:
        payload = await connection.scalar(
            select(Message.snapshot).where(
                Message.message_id == message_id,
                Message.channel_id == channel_id,
            )
        )
    return MessageSnapshot.model_validate(payload) if payload else None


async def mark_deleted(engine: AsyncEngine, channel_id: str, message_ids: list[str]) -> None:
    """事务保存删除墓碑和消息标记；重复删除幂等，正文、图片和版本完整保留。"""
    if not message_ids:
        return
    now = datetime.now(UTC)
    async with engine.begin() as connection:
        # 批量操作固定锁顺序，避免两次交叉删除互相等待。
        for message_id in sorted(set(message_ids)):
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:id, 0))"), {"id": message_id}
            )
        await connection.execute(
            insert(MessageDeletion)
            .values(
                [
                    {"message_id": message_id, "channel_id": channel_id, "observed_at": now}
                    for message_id in set(message_ids)
                ]
            )
            .on_conflict_do_nothing()
        )
        await connection.execute(
            update(Message)
            .where(
                Message.channel_id == channel_id,
                Message.message_id.in_(message_ids),
            )
            .values(deleted_at=func.coalesce(Message.deleted_at, now))
        )
