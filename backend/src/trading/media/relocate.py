"""显式迁移旧 R2 目录：验证复制、事务切换引用、最后清理，支持中断后继续。"""

import asyncio
import logging
from collections import defaultdict

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from trading.db.models import MediaArchive, MediaObject, Message
from trading.media.layout import LEGACY_PREFIX, image_object_key, is_legacy_key
from trading.media.storage import R2Storage

logger = logging.getLogger(__name__)
RELOCATION_LOCK = 729_450_601


async def relocate_object(engine: AsyncEngine, storage: R2Storage, old: dict) -> int:
    """将旧对象各频道/月引用分别复制并切换；失败保留旧原图，重跑只处理剩余引用。"""
    async with engine.connect() as connection:
        references = (
            (
                await connection.execute(
                    select(
                        MediaArchive.id,
                        Message.channel_id,
                        Message.created_at,
                    )
                    .join(Message, Message.message_id == MediaArchive.message_id)
                    .where(MediaArchive.object_key == old["object_key"])
                )
            )
            .mappings()
            .all()
        )
    groups: dict[str, list[str]] = defaultdict(list)
    for reference in references:
        key = image_object_key(
            reference["channel_id"], reference["created_at"], old["digest"], old["content_type"]
        )
        groups[key].append(reference["id"])
    for new_key, archive_ids in groups.items():
        await storage.copy_verified(old["object_key"], new_key, old["digest"], old["size_bytes"])
        async with engine.begin() as connection:
            await connection.execute(
                insert(MediaObject)
                .values(
                    object_key=new_key,
                    digest=old["digest"],
                    size_bytes=old["size_bytes"],
                    content_type=old["content_type"],
                    stored_at=old["stored_at"],
                )
                .on_conflict_do_nothing()
            )
            await connection.execute(
                update(MediaArchive)
                .where(
                    MediaArchive.id.in_(archive_ids),
                    MediaArchive.object_key == old["object_key"],
                )
                .values(object_key=new_key)
            )
    async with engine.connect() as connection:
        remaining = await connection.scalar(
            select(func.count())
            .select_from(MediaArchive)
            .where(
                MediaArchive.object_key == old["object_key"],
            )
        )
        # 上次可能在数据库切换后、旧文件删除前中断；再次核验目标后才继续清理。
        replacements = []
        if not references:
            replacements = (
                (
                    await connection.execute(
                        select(MediaObject.__table__)
                        .join(
                            MediaArchive,
                            MediaArchive.object_key == MediaObject.object_key,
                        )
                        .where(
                            MediaObject.digest == old["digest"],
                            MediaObject.object_key != old["object_key"],
                        )
                        .distinct()
                    )
                )
                .mappings()
                .all()
            )
    if remaining:
        raise RuntimeError("Legacy object still has message references")
    for replacement in replacements:
        await asyncio.to_thread(
            storage.verify_object, replacement["object_key"], old["digest"], old["size_bytes"]
        )
    await storage.delete_legacy(old["object_key"])
    async with engine.begin() as connection:
        await connection.execute(
            delete(MediaObject).where(MediaObject.object_key == old["object_key"])
        )
    return len(groups)


async def reorganize_media(engine: AsyncEngine, storage: R2Storage) -> dict[str, int]:
    """执行用户授权的旧目录迁移；拒绝未知旧目录文件，不触及新目录或其他桶内容。"""
    async with engine.connect() as lock_connection:
        locked = await lock_connection.scalar(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": RELOCATION_LOCK}
        )
        if not locked:
            raise RuntimeError("Media relocation is already running")
        try:
            inventory = await storage.legacy_keys()
            if any(not is_legacy_key(key) for key in inventory):
                raise RuntimeError("Legacy prefix contains files outside the generated layout")
            async with engine.connect() as connection:
                objects = (
                    (
                        await connection.execute(
                            select(MediaObject.__table__)
                            .where(
                                MediaObject.object_key.startswith(LEGACY_PREFIX),
                            )
                            .order_by(MediaObject.object_key)
                        )
                    )
                    .mappings()
                    .all()
                )
            copied = 0
            for index, old in enumerate(objects, start=1):
                if not is_legacy_key(old["object_key"]):
                    raise RuntimeError("Unexpected legacy object key")
                copied += await relocate_object(engine, storage, dict(old))
                if index % 25 == 0 or index == len(objects):
                    logger.info(
                        "media_relocation progress=%s/%s new_objects=%s",
                        index,
                        len(objects),
                        copied,
                    )
            # 上传已完成但数据库尚未提交就退出的旧残留，也只清理精确旧哈希命名空间。
            leftovers = await storage.legacy_keys()
            for key in leftovers:
                if not is_legacy_key(key):
                    raise RuntimeError("Unexpected object appeared in legacy prefix")
                async with engine.connect() as connection:
                    referenced = await connection.scalar(
                        select(func.count())
                        .select_from(MediaArchive)
                        .where(MediaArchive.object_key == key)
                    )
                if referenced:
                    raise RuntimeError("Refusing deletion of a referenced leftover")
                await storage.delete_legacy(key)
            remaining_keys = await storage.legacy_keys()
            if remaining_keys:
                raise RuntimeError("Legacy prefix cleanup is incomplete")
            return {
                "migrated_old_objects": len(objects),
                "new_objects": copied,
                "removed_leftovers": len(leftovers),
                "remaining_old_objects": 0,
            }
        finally:
            await lock_connection.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": RELOCATION_LOCK}
            )
