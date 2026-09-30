"""图片归档的持久队列、租约、去重对象和容量查询；所有状态以数据库为准。"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from trading.db.models import MediaArchive, MediaObject, Message, MessageVersion
from trading.media.candidates import image_candidates
from trading.media.layout import image_object_key

MAX_ATTEMPTS = 5


async def enqueue_images(
    connection: AsyncConnection, snapshot: dict, refresh_url: bool = True
) -> None:
    """在调用方的消息事务中追加归档任务，重复链接只刷新待办 URL。"""
    now = datetime.now(UTC)
    for image in image_candidates(snapshot):
        statement = insert(MediaArchive).values(
            id=str(uuid4()),
            message_id=snapshot["message_id"],
            media_key=image.key,
            source_url=image.url,
            status="pending",
            attempts=0,
            next_attempt_at=now,
            created_at=now,
            updated_at=now,
        )
        if not refresh_url:
            await connection.execute(statement.on_conflict_do_nothing())
            continue
        await connection.execute(
            statement.on_conflict_do_update(
                index_elements=[MediaArchive.message_id, MediaArchive.media_key],
                set_={"source_url": statement.excluded.source_url},
                where=MediaArchive.status != "stored",
            )
        )


async def seed_historical_images(engine: AsyncEngine) -> None:
    """分批扫描当前与历史快照补建任务；重启重复扫描由唯一索引去重。"""
    for model in (Message, MessageVersion):
        cursor = None
        while True:
            statement = select(model.snapshot, model.message_id)
            if model is MessageVersion:
                statement = statement.add_columns(model.fingerprint).order_by(
                    model.message_id, model.fingerprint
                )
                if cursor:
                    statement = statement.where(
                        or_(
                            model.message_id > cursor[0],
                            and_(model.message_id == cursor[0], model.fingerprint > cursor[1]),
                        )
                    )
            else:
                statement = statement.order_by(model.message_id)
                if cursor:
                    statement = statement.where(model.message_id > cursor[0])
            async with engine.begin() as connection:
                rows = (await connection.execute(statement.limit(100))).all()
                for row in rows:
                    await enqueue_images(connection, row.snapshot, refresh_url=False)
            if not rows:
                break
            cursor = (
                (rows[-1].message_id, rows[-1].fingerprint)
                if model is MessageVersion
                else (rows[-1].message_id,)
            )


async def claim_image(engine: AsyncEngine) -> dict | None:
    """行锁领取最早到期任务，并回收进程退出后超时的租约。"""
    now = datetime.now(UTC)
    async with engine.begin() as connection:
        row = (
            (
                await connection.execute(
                    select(
                        MediaArchive.__table__,
                        Message.channel_id,
                        Message.created_at.label("message_created_at"),
                    )
                    .join(Message, Message.message_id == MediaArchive.message_id)
                    .where(
                        or_(
                            and_(
                                MediaArchive.status == "pending",
                                MediaArchive.next_attempt_at <= now,
                            ),
                            and_(
                                MediaArchive.status == "processing", MediaArchive.lease_until <= now
                            ),
                        )
                    )
                    .order_by(Message.created_at.desc(), MediaArchive.next_attempt_at)
                    .limit(1)
                    .with_for_update(skip_locked=True, of=MediaArchive)
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        if row["attempts"] >= MAX_ATTEMPTS:
            await connection.execute(
                update(MediaArchive)
                .where(MediaArchive.id == row["id"])
                .values(
                    status="failed",
                    lease_until=None,
                    last_error="归档任务多次中断，已停止自动重试",
                    updated_at=now,
                )
            )
            return None
        lease = now + timedelta(minutes=5)
        attempts = row["attempts"] + 1
        await connection.execute(
            update(MediaArchive)
            .where(MediaArchive.id == row["id"])
            .values(
                status="processing",
                attempts=attempts,
                lease_until=lease,
                updated_at=now,
            )
        )
        return dict(row) | {"attempts": attempts, "lease_until": lease}


async def fail_image(engine: AsyncEngine, job: dict, reason: str, terminal: bool = False) -> None:
    """记录脱敏原因，按次数退避；不可恢复或五次失败后等待人工重试。"""
    now = datetime.now(UTC)
    async with engine.begin() as connection:
        await connection.execute(
            update(MediaArchive)
            .where(
                MediaArchive.id == job["id"],
                MediaArchive.lease_until == job["lease_until"],
            )
            .values(
                status="failed" if terminal or job["attempts"] >= MAX_ATTEMPTS else "pending",
                lease_until=None,
                last_error=reason,
                updated_at=now,
                next_attempt_at=now + timedelta(seconds=min(60 * 2 ** (job["attempts"] - 1), 3600)),
            )
        )


async def finish_image(
    engine: AsyncEngine, job: dict, digest: str, size: int, content_type: str
) -> None:
    """上传成功后提交去重对象及任务引用；旧租约不覆盖新任务状态。"""
    now = datetime.now(UTC)
    object_key = image_object_key(
        job["channel_id"], job["message_created_at"], digest, content_type
    )
    async with engine.begin() as connection:
        await connection.execute(
            insert(MediaObject)
            .values(
                digest=digest,
                object_key=object_key,
                size_bytes=size,
                content_type=content_type,
                stored_at=now,
            )
            .on_conflict_do_nothing()
        )
        await connection.execute(
            update(MediaArchive)
            .where(
                MediaArchive.id == job["id"],
                MediaArchive.lease_until == job["lease_until"],
            )
            .values(
                status="stored",
                object_key=object_key,
                lease_until=None,
                last_error=None,
                updated_at=now,
            )
        )


async def retry_failed_images(engine: AsyncEngine) -> int:
    """用户主动重试失败任务，清零次数；不重新上传已成功归档的图片。"""
    now = datetime.now(UTC)
    async with engine.begin() as connection:
        result = await connection.execute(
            update(MediaArchive)
            .where(MediaArchive.status == "failed")
            .values(
                status="pending",
                attempts=0,
                next_attempt_at=now,
                last_error=None,
                updated_at=now,
            )
        )
        return result.rowcount


async def storage_summary(engine: AsyncEngine, configured: bool, warning_bytes: int) -> dict:
    """统计本项目数据库已确认的 R2 对象，容量告警不停止归档或删除原图。"""
    async with engine.connect() as connection:
        objects = (
            await connection.execute(
                select(func.count(), func.coalesce(func.sum(MediaObject.size_bytes), 0))
            )
        ).one()
        states = dict(
            (
                await connection.execute(
                    select(MediaArchive.status, func.count()).group_by(MediaArchive.status)
                )
            ).all()
        )
        error = await connection.scalar(
            select(MediaArchive.last_error)
            .where(MediaArchive.last_error.is_not(None))
            .order_by(MediaArchive.updated_at.desc())
            .limit(1)
        )
    return {
        "configured": configured,
        "object_count": objects[0],
        "size_bytes": objects[1],
        "warning_bytes": warning_bytes,
        "capacity_warning": objects[1] >= warning_bytes,
        "pending": states.get("pending", 0),
        "processing": states.get("processing", 0),
        "stored": states.get("stored", 0),
        "failed": states.get("failed", 0),
        "last_error": error,
    }
