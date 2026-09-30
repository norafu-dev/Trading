"""验证旧图片目录迁移、复制失败保护和中断后的继续清理，不连接真实 R2。"""

import hashlib
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, update

from trading.collector.messages import MessageSnapshot
from trading.db.models import MediaArchive, MediaObject, MessageVersion
from trading.db.repository import store_snapshot
from trading.media.layout import LEGACY_PREFIX, image_object_key
from trading.media.relocate import reorganize_media

pytestmark = pytest.mark.integration
DATA = b"original PNG image bytes"
DIGEST = hashlib.sha256(DATA).hexdigest()
OLD_KEY = f"{LEGACY_PREFIX}{DIGEST[:2]}/{DIGEST}"
CREATED = datetime(2026, 9, 17, tzinfo=UTC)


class MemoryStorage:
    """用内存对象模拟复制校验和删除失败，记录每次操作以验证安全顺序。"""

    def __init__(self):
        """预置旧原图，默认允许复制和删除。"""
        self.objects = {OLD_KEY: DATA}
        self.calls = []
        self.fail_copy = False
        self.fail_delete = False

    async def legacy_keys(self):
        """只返回旧前缀对象，让新目录始终不进入清理集合。"""
        return [key for key in self.objects if key.startswith(LEGACY_PREFIX)]

    def verify_object(self, key, digest, size):
        """模拟完整字节核验，避免测试仅断言实现的调用次数。"""
        data = self.objects[key]
        assert hashlib.sha256(data).hexdigest() == digest and len(data) == size
        self.calls.append(("verify", key))

    async def copy_verified(self, source, target, digest, size):
        """复制目标后核验，注入失败时保留源文件。"""
        self.objects[target] = self.objects[source]
        if self.fail_copy:
            raise ValueError("verification failed")
        self.verify_object(target, digest, size)

    async def delete_legacy(self, key):
        """模拟远端删除暂时失败；成功后移除旧文件。"""
        if self.fail_delete:
            raise OSError("temporary deletion failure")
        self.calls.append(("delete", key))
        self.objects.pop(key, None)


async def seed_legacy(engine):
    """建立两频道共用旧原图的真实数据库引用，保留两条原消息版本。"""
    for channel in ("20", "21"):
        await store_snapshot(
            engine,
            MessageSnapshot(
                message_id=f"1{channel}",
                guild_id=None,
                channel_id=channel,
                thread_id=None,
                parent_channel_id=None,
                author_id="30",
                content="原消息",
                created_at=CREATED,
                attachments=[
                    {
                        "url": f"https://cdn.discordapp.com/attachments/{channel}/40/chart.png",
                        "content_type": "image/png",
                    }
                ],
                embeds=[],
            ),
        )
    async with engine.begin() as connection:
        await connection.execute(
            MediaObject.__table__.insert().values(
                digest=DIGEST,
                object_key=OLD_KEY,
                size_bytes=len(DATA),
                content_type="image/png",
                stored_at=CREATED,
            )
        )
        await connection.execute(update(MediaArchive).values(status="stored", object_key=OLD_KEY))


async def test_relocation_separates_channels_and_preserves_message_history(engine):
    """实际消息引用按频道切换，完整原图先验证后删除，重跑不会再写文件。"""
    await seed_legacy(engine)
    storage = MemoryStorage()
    result = await reorganize_media(engine, storage)
    expected = {image_object_key(channel, CREATED, DIGEST, "image/png") for channel in ("20", "21")}
    assert result["migrated_old_objects"] == 1 and result["new_objects"] == 2
    assert set(storage.objects) == expected
    assert storage.calls[-1] == ("delete", OLD_KEY)
    async with engine.connect() as connection:
        assert set((await connection.scalars(select(MediaArchive.object_key))).all()) == expected
        assert await connection.scalar(select(func.count()).select_from(MediaObject)) == 2
        assert await connection.scalar(select(func.count()).select_from(MessageVersion)) == 2
    assert (await reorganize_media(engine, storage))["migrated_old_objects"] == 0


async def test_copy_failure_keeps_old_references_and_can_be_retried(engine):
    """新文件未校验通过时不切换引用、不删旧图；下一次重跑可完成迁移。"""
    await seed_legacy(engine)
    storage = MemoryStorage()
    storage.fail_copy = True
    with pytest.raises(ValueError):
        await reorganize_media(engine, storage)
    async with engine.connect() as connection:
        assert set((await connection.scalars(select(MediaArchive.object_key))).all()) == {OLD_KEY}
    assert OLD_KEY in storage.objects and not storage.calls
    storage.fail_copy = False
    assert (await reorganize_media(engine, storage))["remaining_old_objects"] == 0


async def test_delete_failure_resumes_after_reference_switch(engine):
    """数据库已切换后删除失败，重跑再次核验目标并清除旧图，不遗失引用。"""
    await seed_legacy(engine)
    storage = MemoryStorage()
    storage.fail_delete = True
    with pytest.raises(OSError):
        await reorganize_media(engine, storage)
    async with engine.connect() as connection:
        assert await connection.scalar(select(func.count()).select_from(MediaObject)) == 3
        assert OLD_KEY not in (await connection.scalars(select(MediaArchive.object_key))).all()
    storage.calls.clear()
    storage.fail_delete = False
    await reorganize_media(engine, storage)
    assert len(storage.calls) == 3 and storage.calls[-1] == ("delete", OLD_KEY)
    async with engine.connect() as connection:
        assert await connection.scalar(select(func.count()).select_from(MediaObject)) == 2


async def test_cleanup_refuses_unknown_objects_and_preserves_new_paths(engine):
    """未知旧目录文件阻止全部删除；明确旧格式的无引用残留可清理，新路径保留。"""
    storage = MemoryStorage()
    unrelated = f"{LEGACY_PREFIX}notes.txt"
    new_key = image_object_key("20", CREATED, DIGEST, "image/png")
    storage.objects.update({unrelated: b"notes", new_key: DATA})
    with pytest.raises(RuntimeError, match="outside the generated layout"):
        await reorganize_media(engine, storage)
    assert OLD_KEY in storage.objects and not storage.calls
    del storage.objects[unrelated]
    result = await reorganize_media(engine, storage)
    assert result["removed_leftovers"] == 1 and storage.objects == {new_key: DATA}
