"""验证消息过滤、近期补采，以及回调失败后的可见错误状态和关闭行为。"""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from trading.collector.client import Collector
from trading.collector.messages import MessageSnapshot
from trading.config import Sources


async def message_stream(*messages):
    """构造 Discord history 使用的异步消息流，避免单元测试访问网络。"""
    for message in messages:
        yield message


@pytest.mark.asyncio
async def test_unselected_messages_never_reach_normalization_or_storage(monkeypatch):
    """验证未配置作者的消息不会进入标准化或数据库写入阶段。"""
    store = AsyncMock()
    monkeypatch.setattr("trading.collector.client.store_snapshot", store)
    sources = Sources.model_validate(
        {"sources": [{"name": "a", "channel_id": "20", "author_ids": ["30"]}]}
    )
    client = Collector(None, sources)
    await client.on_message(
        SimpleNamespace(channel=SimpleNamespace(id=20), author=SimpleNamespace(id=99))
    )
    store.assert_not_called()


@pytest.mark.asyncio
async def test_backfill_starts_after_latest_saved_message_and_reuses_storage(monkeypatch):
    """验证补采从数据库断点开始，并让历史消息复用实时消息的过滤和写入方法。"""
    sources = Sources.model_validate(
        {"sources": [{"name": "a", "channel_id": "20", "author_ids": ["30"]}]}
    )
    client = Collector(None, sources)
    channel = MagicMock(spec=discord.TextChannel)
    history_message = SimpleNamespace(
        id=41,
        channel=SimpleNamespace(id=20),
        author=SimpleNamespace(id=30),
    )
    channel.history.return_value = message_stream(history_message)
    monkeypatch.setattr(client, "get_channel", lambda channel_id: channel)
    monkeypatch.setattr("trading.collector.client.latest_message_id", AsyncMock(return_value="40"))
    monkeypatch.setattr(
        "trading.collector.client.normalize_message",
        lambda message: MessageSnapshot(
            message_id=str(message.id),
            guild_id="10",
            channel_id=str(message.channel.id),
            thread_id=None,
            parent_channel_id=None,
            author_id=str(message.author.id),
            content="补采消息",
            created_at=datetime(2026, 9, 24, tzinfo=UTC),
        ),
    )
    store = AsyncMock(return_value=True)
    monkeypatch.setattr("trading.collector.client.store_snapshot", store)
    monkeypatch.setattr("trading.collector.client.update_runtime", AsyncMock())
    add_event = AsyncMock()
    monkeypatch.setattr("trading.collector.client.add_event", add_event)

    await client.backfill_sources()

    history_call = channel.history.call_args.kwargs
    assert history_call["after"].id == 40
    assert history_call["oldest_first"] is False
    store.assert_awaited_once()
    assert "新增 1 条" in add_event.await_args.args[1]


@pytest.mark.asyncio
async def test_handler_failure_is_visible_and_stops_client(monkeypatch):
    """验证回调失败会设置错误状态并关闭客户端，避免静默停止采集。"""
    sources = Sources.model_validate(
        {"sources": [{"name": "a", "channel_id": "20", "author_ids": ["30"]}]}
    )
    client = Collector(None, sources)
    close = AsyncMock()
    monkeypatch.setattr(client, "close", close)
    await client.on_error("on_message")
    assert client.failed
    close.assert_awaited_once()
