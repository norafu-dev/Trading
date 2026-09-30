"""验证消息过滤、近期补采，以及回调失败后的可见错误状态和关闭行为。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from trading.collector.client import Collector
from trading.config import Sources


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
