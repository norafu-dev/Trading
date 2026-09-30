"""验证无缓存编辑、删除竞态、补采中断与实时新消息隔离，以及消息来源时效契约。"""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from sqlalchemy import func, select, update

from trading.collector.client import Collector
from trading.collector.history import HistoryRecovery
from trading.collector.messages import MessageSnapshot
from trading.config import Sources
from trading.db.checkpoints import begin_scan, ensure_checkpoint
from trading.db.message_browser import channel_messages
from trading.db.models import ChannelCheckpoint, Message, MessageDeletion, MessageVersion
from trading.db.repository import mark_deleted, store_snapshot

pytestmark = pytest.mark.integration
CREATED = datetime.now(UTC) - timedelta(days=1)


def sample(message_id="400", content="开仓", author_id="30"):
    """构造昨日发布的测试消息，避免真实账号、频道或网络。"""
    return MessageSnapshot(
        message_id=message_id,
        guild_id=None,
        channel_id="20",
        thread_id=None,
        parent_channel_id=None,
        author_id=author_id,
        content=content,
        created_at=CREATED,
    )


def collector(engine):
    """创建只允许频道 20 作者 30 的客户端，不登录 Discord。"""
    return Collector(
        engine,
        Sources.model_validate(
            {
                "sources": [
                    {"name": "测试", "channel_id": "20", "author_ids": ["30"]},
                ]
            }
        ),
    )


async def test_uncached_partial_edits_keep_text_and_versions(engine):
    """无缓存、仅 Embed 的更新仍保留正文，再编辑正文时保留全部历史与来源。"""
    await store_snapshot(engine, sample(), "realtime")
    client = collector(engine)
    await client.on_raw_message_edit(
        SimpleNamespace(
            channel_id=20, message_id=400, data={"embeds": [{"description": "止损 10"}]}
        )
    )
    await client.on_raw_message_edit(
        SimpleNamespace(
            channel_id=20,
            message_id=400,
            data={"content": "撤销开仓", "edited_timestamp": datetime.now(UTC).isoformat()},
        )
    )
    async with engine.connect() as connection:
        row = (await connection.execute(select(Message.__table__))).mappings().one()
        assert (
            row["content"] == "撤销开仓"
            and row["snapshot"]["embeds"][0]["description"] == "止损 10"
        )
        assert row["first_delivery"] == "realtime"
        assert await connection.scalar(select(func.count()).select_from(MessageVersion)) == 3
        assert set((await connection.scalars(select(MessageVersion.observation_source))).all()) == {
            "realtime",
            "edit",
        }


async def test_delete_before_save_and_concurrent_delete_never_revive_messages(engine):
    """删除先到、批量删除、重复删除及并发旧快照都不能抹掉墓碑或历史正文。"""
    client = collector(engine)
    await client.on_raw_bulk_message_delete(SimpleNamespace(channel_id=20, message_ids={400, 401}))
    await store_snapshot(engine, sample(), "backfill")
    await asyncio.gather(
        store_snapshot(engine, sample("401"), "realtime"), mark_deleted(engine, "20", ["401"])
    )
    await store_snapshot(engine, sample("401", "旧消息再次投递"), "backfill")
    await client.on_raw_message_delete(SimpleNamespace(channel_id=20, message_id=401))
    await client.on_raw_message_delete(SimpleNamespace(channel_id=99, message_id=402))
    async with engine.connect() as connection:
        rows = (await connection.execute(select(Message.__table__))).mappings().all()
        assert len(rows) == 2 and all(row["deleted_at"] for row in rows)
        assert await connection.scalar(select(func.count()).select_from(MessageDeletion)) == 2
        assert await connection.scalar(select(func.count()).select_from(MessageVersion)) == 3
    page = await channel_messages(engine, "20", None, 50)
    assert all(message.deleted_at for message in page.messages)


async def history_client(engine, total=1205, fail_after=None):
    """模拟按断点与目标过滤的真实分页服务；可在一页中途注入网络中断。"""
    client = collector(engine)
    channel = MagicMock(spec=discord.TextChannel)

    async def messages(before, limit, oldest_first, after=None):
        """从旧到新生成分页结果，中断后断点只应推进已经成功处理的前缀。"""
        selected = [
            value
            for value in range(401, 401 + total)
            if (after.id if after else 0) < value < before.id
        ]
        selected = sorted(selected, reverse=not oldest_first)[:limit]
        for index, value in enumerate(selected):
            if fail_after is not None and index == fail_after:
                raise OSError("network interrupted")
            yield SimpleNamespace(id=value, created_at=CREATED)

    async def save(message, origin):
        """让模拟历史流使用真实消息事务及来源记录，而不调用 Discord 标准化。"""
        return await store_snapshot(engine, sample(str(message.id)), origin)

    channel.history.side_effect = messages
    client.get_channel = MagicMock(return_value=channel)
    client.store_matching_message = save
    return client


async def test_backlog_over_one_thousand_survives_live_messages_and_restart(engine):
    """超过旧上限的缺口分多页全部补齐，实时新消息不推进补采断点。"""
    await store_snapshot(engine, sample())
    await ensure_checkpoint(engine, "20")
    await store_snapshot(engine, sample("99999"), "realtime")
    first = await begin_scan(engine, "20")
    assert first["cursor_id"] == "399"
    target = first["target_id"]
    worker = HistoryRecovery(await history_client(engine))
    for index in range(13):
        if index == 3:
            await engine.dispose()
            worker = HistoryRecovery(await history_client(engine))
        await worker.scan_channel("20")
    async with engine.connect() as connection:
        row = (await connection.execute(select(ChannelCheckpoint.__table__))).mappings().one()
        assert row["state"] == "idle" and row["cursor_id"] == target and row["target_id"] is None
        assert await connection.scalar(select(func.count()).select_from(Message)) == 1207
        assert (
            await connection.scalar(
                select(Message.first_delivery).where(Message.message_id == "401")
            )
            == "backfill"
        )


async def test_failed_scan_retries_same_target_without_skipping_gap(engine):
    """一页中途断线保留前缀进度与目标，重连后的实时消息不掩盖未处理部分。"""
    await store_snapshot(engine, sample())
    await ensure_checkpoint(engine, "20")
    await HistoryRecovery(await history_client(engine, total=10, fail_after=3)).scan_channel("20")
    async with engine.connect() as connection:
        before = (await connection.execute(select(ChannelCheckpoint.__table__))).mappings().one()
        assert (
            before["state"] == "error" and before["cursor_id"] == "403" and before["attempts"] == 1
        )
    assert await begin_scan(engine, "20") is None
    await store_snapshot(engine, sample("99999"), "realtime")
    async with engine.begin() as connection:
        await connection.execute(
            update(ChannelCheckpoint).values(
                next_attempt_at=datetime.now(UTC) - timedelta(seconds=1)
            )
        )
    await engine.dispose()
    await HistoryRecovery(await history_client(engine, total=10)).scan_channel("20")
    async with engine.connect() as connection:
        after = (await connection.execute(select(ChannelCheckpoint.__table__))).mappings().one()
        assert after["state"] == "idle" and after["cursor_id"] == before["target_id"]
        assert after["attempts"] == 0 and after["last_error"] is None
        assert await connection.scalar(select(func.count()).select_from(Message)) == 12


async def test_first_delivery_is_not_reclassified_and_freshness_is_only_a_hint(engine):
    """重复投递不改首次来源，迟到消息显示延迟；新鲜编辑保留历史来源而不伪装实时。"""
    original = sample()
    await store_snapshot(engine, original, "backfill")
    await store_snapshot(engine, original, "realtime")
    page = await channel_messages(engine, "20", None, 50, freshness_seconds=120)
    assert page.messages[0].first_delivery == "backfill" and page.messages[0].is_stale
    assert page.messages[0].collection_delay_seconds > 80000
    await store_snapshot(
        engine,
        original.model_copy(update={"content": "更新止损", "edited_at": datetime.now(UTC)}),
        "edit",
    )
    page = await channel_messages(engine, "20", None, 50)
    assert page.messages[0].first_delivery == "backfill" and not page.messages[0].is_stale
    assert page.messages[0].edited_at is not None


async def test_new_channel_initializes_recent_window_without_recovering_all_old_history(engine):
    """新来源保留最近千条的原有范围，初始化后独立游标记录实际覆盖起点。"""
    await ensure_checkpoint(engine, "20")
    worker = HistoryRecovery(await history_client(engine))
    for _ in range(11):
        await worker.scan_channel("20")
    async with engine.connect() as connection:
        assert await connection.scalar(select(func.count()).select_from(Message)) == 1000
        ids = set((await connection.scalars(select(Message.message_id))).all())
        assert "401" not in ids and "606" in ids and "1605" in ids
        checkpoint = (
            (await connection.execute(select(ChannelCheckpoint.__table__))).mappings().one()
        )
        assert checkpoint["state"] == "idle" and checkpoint["coverage_started_at"] == CREATED


async def test_filtered_history_still_advances_scan_without_inventing_messages(engine):
    """扫描作者不命中的消息也推进完整性检查，但不把它们写入采集样本。"""
    await store_snapshot(engine, sample())
    await ensure_checkpoint(engine, "20")
    client = await history_client(engine, total=10)
    client.store_matching_message = AsyncMock(return_value=False)
    await HistoryRecovery(client).scan_channel("20")
    async with engine.connect() as connection:
        assert await connection.scalar(select(func.count()).select_from(Message)) == 1
        assert await connection.scalar(select(ChannelCheckpoint.state)) == "idle"


async def test_uncached_unseen_edit_fetches_full_message_and_filters_author(engine, monkeypatch):
    """尚未留存的局部编辑读取完整消息，作者未命中时不入库，命中时标记补采来源。"""
    client = collector(engine)
    channel = MagicMock(spec=discord.TextChannel)
    message = SimpleNamespace(id=400, channel=SimpleNamespace(id=20), author=SimpleNamespace(id=99))
    channel.fetch_message = AsyncMock(return_value=message)
    monkeypatch.setattr(client, "get_channel", MagicMock(return_value=channel))
    monkeypatch.setattr("trading.collector.client.normalize_message", lambda message: sample())
    event = SimpleNamespace(channel_id=20, message_id=400, data={"content": "已编辑"})
    await client.on_raw_message_edit(event)
    async with engine.connect() as connection:
        assert await connection.scalar(select(func.count()).select_from(Message)) == 0
    message.author.id = 30
    await client.on_raw_message_edit(event)
    async with engine.connect() as connection:
        assert await connection.scalar(select(Message.first_delivery)) == "backfill"
