"""使用真实 PostgreSQL 验证并发去重、重复投递与乱序快照留存。"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from trading.collector.messages import MessageSnapshot
from trading.db.models import Message, MessageVersion
from trading.db.repository import latest_message_id, store_snapshot

pytestmark = pytest.mark.integration


def snapshot(content="original", edited_at=None):
    """构造可覆写字段的消息快照，供数据库幂等与版本测试使用。"""
    return MessageSnapshot(
        message_id="9007199254740993",
        guild_id="10",
        channel_id="20",
        thread_id=None,
        parent_channel_id=None,
        author_id="30",
        content=content,
        created_at=datetime(2026, 9, 17, tzinfo=UTC),
        edited_at=edited_at,
    )


async def counts(engine):
    """读取当前消息和版本数量，用来验证去重后的数据库结果。"""
    async with engine.connect() as connection:
        return (
            await connection.scalar(select(func.count()).select_from(Message)),
            await connection.scalar(select(func.count()).select_from(MessageVersion)),
        )


async def test_duplicate_delivery_and_connection_restart_are_idempotent(engine):
    """验证重复投递和重新建立数据库连接不会新增重复消息或版本。"""
    assert await store_snapshot(engine, snapshot())
    await engine.dispose()
    assert not await store_snapshot(engine, snapshot())
    assert await counts(engine) == (1, 1)


async def test_concurrent_duplicate_delivery_creates_one_version(engine):
    """验证并发写入同一快照时，唯一约束仍保证只有一个版本。"""
    results = await asyncio.gather(*(store_snapshot(engine, snapshot()) for _ in range(8)))
    assert sum(results) == 1
    assert await counts(engine) == (1, 1)


async def test_stale_snapshot_keeps_newer_content_and_both_versions(engine):
    """验证旧快照被保留为历史，但不能替换当前的新内容。"""
    old = snapshot()
    new = snapshot("updated stop", old.created_at + timedelta(minutes=1))
    assert await store_snapshot(engine, new)
    assert await store_snapshot(engine, old)
    assert await counts(engine) == (1, 2)
    async with engine.connect() as connection:
        assert await connection.scalar(select(Message.content)) == "updated stop"


async def test_changed_message_keeps_original_version(engine):
    """验证内容更新后保留原始版本，并正确更新当前消息。"""
    old = snapshot()
    await store_snapshot(engine, old)
    await store_snapshot(engine, snapshot("closed", old.created_at + timedelta(minutes=1)))
    assert await counts(engine) == (1, 2)
    async with engine.connect() as connection:
        versions = (await connection.execute(select(MessageVersion.snapshot))).scalars().all()
    assert {v["content"] for v in versions} == {"original", "closed"}


async def test_latest_message_id_uses_channel_and_creation_time(engine):
    """验证启动补采只使用目标频道内创建时间最新的已保存消息作为断点。"""
    first = snapshot()
    other_channel = first.model_copy(
        update={
            "message_id": "9007199254740994",
            "channel_id": "21",
            "created_at": first.created_at + timedelta(minutes=2),
        }
    )
    latest = first.model_copy(
        update={
            "message_id": "9007199254740995",
            "created_at": first.created_at + timedelta(minutes=1),
        }
    )
    await store_snapshot(engine, first)
    await store_snapshot(engine, other_channel)
    await store_snapshot(engine, latest)
    assert await latest_message_id(engine, "20") == latest.message_id
    assert await latest_message_id(engine, "22") is None
