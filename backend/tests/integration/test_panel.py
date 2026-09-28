"""验证面板接口、配置事务、心跳解释与 Collector 来源热更新。"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import httpx
import pytest
import pytest_asyncio

from trading.api import create_app
from trading.collector.client import Collector
from trading.collector.messages import MessageSnapshot
from trading.db.control import update_runtime
from trading.db.repository import store_snapshot

pytestmark = pytest.mark.integration
BODY = {
    "name": "Trader A",
    "kol_name": "Alpha KOL",
    "group_id": None,
    "position": 0,
    "channel_id": "123456789012345678",
    "author_ids": ["234567890123456789"],
    "enabled": True,
}


@pytest_asyncio.fixture
async def client(engine):
    """以真实应用生命周期创建异步测试客户端，携带本机面板要求的请求头。"""
    app = create_app()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            headers={"X-Requested-With": "trading-panel"},
        ) as client:
            yield client


async def test_source_crud_and_duplicate_validation(client):
    """验证来源增改删、重复频道冲突和非法作者输入。"""
    response = await client.post("/api/sources", json=BODY)
    assert response.status_code == 201
    source = response.json()
    assert source["status"] == "pending"
    assert source["kol_name"] == "Alpha KOL"
    assert (await client.post("/api/sources", json=BODY)).status_code == 409
    assert (await client.post("/api/sources", json={**BODY, "author_ids": []})).status_code == 422
    updated = await client.put(f"/api/sources/{source['id']}", json={**BODY, "enabled": False})
    assert updated.status_code == 200
    assert updated.json()["enabled"] is False
    data = (await client.get("/api/dashboard")).json()
    assert len(data["sources"]) == 1
    assert data["sources"][0]["channel_id"] == BODY["channel_id"]
    assert (await client.delete(f"/api/sources/{source['id']}")).status_code == 204
    assert (await client.get("/api/dashboard")).json()["sources"] == []


async def test_runtime_distinguishes_missing_token_from_stale_and_connected(client, engine):
    """验证缺 Token、心跳过期和正常连接在面板中显示不同状态。"""
    await update_runtime(engine, state="missing_token", heartbeat_at=datetime.now(UTC))
    runtime = (await client.get("/api/dashboard")).json()["runtime"]
    assert runtime["state"] == "missing_token" and runtime["process_alive"]
    await update_runtime(
        engine, state="connected", heartbeat_at=datetime.now(UTC) - timedelta(seconds=40)
    )
    runtime = (await client.get("/api/dashboard")).json()["runtime"]
    assert runtime["state"] == "stale" and not runtime["process_alive"]
    await update_runtime(engine, state="connected", heartbeat_at=datetime.now(UTC))
    runtime = (await client.get("/api/dashboard")).json()["runtime"]
    assert runtime["state"] == "connected" and runtime["process_alive"]


async def test_mutations_reject_cross_origin_and_form_requests(client):
    """验证跨站写请求和缺少指定请求头的写请求被拒绝。"""
    response = await client.post(
        "/api/sources", json=BODY, headers={"Origin": "https://example.org"}
    )
    assert response.status_code == 403
    response = await client.post("/api/sources", json=BODY, headers={"X-Requested-With": ""})
    assert response.status_code == 403


async def test_delete_source_preserves_collected_messages(client, engine):
    """验证移除采集来源只影响配置，不会删除历史消息。"""
    source = (await client.post("/api/sources", json=BODY)).json()
    await store_snapshot(
        engine,
        MessageSnapshot(
            message_id="345678901234567890",
            guild_id="456789012345678901",
            channel_id=BODY["channel_id"],
            author_id=BODY["author_ids"][0],
            thread_id=None,
            parent_channel_id=None,
            content="original message",
            created_at=datetime.now(UTC),
        ),
    )
    await client.delete(f"/api/sources/{source['id']}")
    data = (await client.get("/api/dashboard")).json()
    assert data["total_messages"] == 1
    assert data["messages"][0]["content"] == "original message"


async def test_collector_reloads_sources_and_isolates_invalid_channel(client, engine, monkeypatch):
    """验证热更新配置时无效频道被隔离，有效频道仍正常加载。"""
    good = (await client.post("/api/sources", json=BODY)).json()
    bad_body = {**BODY, "name": "invalid", "channel_id": "999999999999999999"}
    await client.post("/api/sources", json=bad_body)
    collector = Collector(engine)
    channel = MagicMock(spec=discord.TextChannel)
    channel.guild = SimpleNamespace(subscribe=AsyncMock())
    monkeypatch.setattr(
        collector, "get_channel", lambda id: channel if str(id) == BODY["channel_id"] else object()
    )
    await collector.sync_sources()
    assert collector.sources.matches(BODY["channel_id"], BODY["author_ids"][0])
    assert not collector.sources.matches(bad_body["channel_id"], BODY["author_ids"][0])
    data = (await client.get("/api/dashboard")).json()
    assert {s["status"] for s in data["sources"]} == {"ready", "error"}
    await client.put(f"/api/sources/{good['id']}", json={**BODY, "enabled": False})
    await collector.sync_sources()
    assert not collector.sources.matches(BODY["channel_id"], BODY["author_ids"][0])
    assert (await client.get("/api/dashboard")).json()["runtime"]["active_sources"] == 0


async def test_source_update_rolls_back_when_audit_write_fails(client, monkeypatch):
    """验证审计写入失败时，来源更新和审计记录整体回滚。"""
    from sqlalchemy.exc import SQLAlchemyError

    from trading.services import sources

    source = (await client.post("/api/sources", json=BODY)).json()
    before = (await client.get("/api/dashboard")).json()
    monkeypatch.setattr(
        sources, "record_source_event", AsyncMock(side_effect=SQLAlchemyError("audit unavailable"))
    )
    response = await client.put(
        f"/api/sources/{source['id']}", json={**BODY, "name": "Must roll back"}
    )
    assert response.status_code == 503
    after = (await client.get("/api/dashboard")).json()
    assert after["sources"] == before["sources"]
    assert after["events"] == before["events"]


async def test_changed_source_is_revalidated_without_restarting_collector(
    client, engine, monkeypatch
):
    """验证缓存只复用未变更配置，修改作者后无需重启即可重新加载。"""
    source = (await client.post("/api/sources", json=BODY)).json()
    collector = Collector(engine)
    channel = MagicMock(spec=discord.TextChannel)
    channel.guild = SimpleNamespace(subscribe=AsyncMock())
    lookup = MagicMock(return_value=channel)
    monkeypatch.setattr(collector, "get_channel", lookup)
    await collector.sync_sources()
    await collector.sync_sources()
    assert lookup.call_count == 1

    new_author = "345678901234567890"
    await client.put(f"/api/sources/{source['id']}", json={**BODY, "author_ids": [new_author]})
    await collector.sync_sources()
    assert lookup.call_count == 2
    assert collector.sources.matches(BODY["channel_id"], new_author)
    assert not collector.sources.matches(BODY["channel_id"], BODY["author_ids"][0])


async def test_missing_source_does_not_create_audit_event(client):
    """验证更新或删除不存在来源返回 404，且不制造成功审计事件。"""
    missing_id = "00000000-0000-4000-8000-000000000000"
    before = (await client.get("/api/dashboard")).json()
    assert (await client.put(f"/api/sources/{missing_id}", json=BODY)).status_code == 404
    assert (await client.delete(f"/api/sources/{missing_id}")).status_code == 404
    after = (await client.get("/api/dashboard")).json()
    assert after["sources"] == before["sources"]
    assert after["events"] == before["events"]


async def test_message_browser_filters_channel_and_paginates(client, engine):
    """验证聊天页不受概览 20 条限制，按频道汇总作者并使用精确 ID 分页。"""
    for index in range(55):
        await store_snapshot(
            engine,
            MessageSnapshot(
                message_id=str(9007199254740993 + index),
                guild_id="10",
                channel_id="20",
                thread_id=None,
                parent_channel_id=None,
                author_id="30",
                content=f"message {index}",
                author_name="Trader A",
                channel_name="signals",
                author_avatar_url="https://cdn.discordapp.com/embed/avatars/0.png",
                created_at=datetime.now(UTC),
            ),
        )
    await store_snapshot(
        engine,
        MessageSnapshot(
            message_id="9007199254741999",
            guild_id="10",
            channel_id="20",
            author_id="31",
            thread_id=None,
            parent_channel_id=None,
            content="different author",
            created_at=datetime.now(UTC),
        ),
    )
    response = await client.get("/api/messages", params={"channel_id": "20"})
    assert response.status_code == 200
    page = response.json()
    assert len(page["messages"]) == 50
    assert page["messages"][0]["content"] == "message 6"
    assert page["messages"][-1]["content"] == "different author"
    assert page["messages"][0]["author_name"] == "Trader A"
    older = (
        await client.get(
            "/api/messages",
            params={"channel_id": "20", "before": page["next_before"]},
        )
    ).json()
    assert [item["content"] for item in older["messages"]] == [
        f"message {index}" for index in range(6)
    ]
    assert older["next_before"] is None
    assert (await client.get("/api/messages", params={"channel_id": "21"})).json()["messages"] == []


async def test_navigation_includes_empty_sources_and_retained_history(client, engine):
    """验证未收消息的频道可见，且删除来源后仍能从未分组区域读取历史。"""
    source = (await client.post("/api/sources", json=BODY)).json()
    navigation = (await client.get("/api/messages/navigation")).json()
    assert navigation["ungrouped"][0]["message_count"] == 0
    await store_snapshot(
        engine,
        MessageSnapshot(
            message_id="345678901234567890",
            guild_id="10",
            channel_id=BODY["channel_id"],
            author_id=BODY["author_ids"][0],
            content="saved",
            created_at=datetime.now(UTC),
            thread_id=None,
            parent_channel_id=None,
            author_name="Trader A",
            channel_name="real-channel",
        ),
    )
    await client.post("/api/sources", json={**BODY, "channel_id": "123456789012345679"})
    await client.delete(f"/api/sources/{source['id']}")
    navigation = (await client.get("/api/messages/navigation")).json()
    assert len(navigation["ungrouped"]) == 2
    archived = next(
        item for item in navigation["ungrouped"] if item["channel_id"] == BODY["channel_id"]
    )
    assert archived["archived"] is True
    assert archived["name"] == "real-channel"
    assert archived["message_count"] == 1


async def test_message_browser_handles_legacy_profiles_and_validates_query(client, engine):
    """验证旧快照缺少昵称时使用作者 ID，且非法分页输入会被拒绝。"""
    await store_snapshot(
        engine,
        MessageSnapshot(
            message_id="9007199254740993",
            guild_id="10",
            channel_id="20",
            author_id="30",
            thread_id=None,
            parent_channel_id=None,
            content="legacy",
            created_at=datetime.now(UTC),
            author_avatar_url="https://example.org/tracking.png",
        ),
    )
    page = (await client.get("/api/messages", params={"channel_id": "20"})).json()
    assert page["messages"][0]["author_name"] == "30"
    assert (
        await client.get("/api/messages", params={"channel_id": "20", "limit": 101})
    ).status_code == 422
    assert (
        await client.get("/api/messages", params={"channel_id": "20", "before": "invalid"})
    ).status_code == 422


async def test_configured_name_and_discord_media_are_returned(client, engine):
    """验证配置的显示名字优先于 Discord 快照，并返回可展示附件与 Embed。"""
    await client.post("/api/sources", json=BODY)
    await store_snapshot(
        engine,
        MessageSnapshot(
            message_id="9007199254740994",
            guild_id="10",
            channel_id=BODY["channel_id"],
            author_id=BODY["author_ids"][0],
            thread_id=None,
            parent_channel_id=None,
            content="media",
            created_at=datetime.now(UTC),
            author_name="Discord nickname",
            author_avatar_url="https://cdn.discordapp.com/embed/avatars/0.png",
            attachments=[
                {
                    "filename": "chart.png",
                    "content_type": "image/png",
                    "url": "https://cdn.discordapp.com/attachments/1/2/chart.png",
                }
            ],
            embeds=[
                {
                    "title": "Signal chart",
                    "image": {
                        "proxy_url": "https://images-ext-1.discordapp.net/external/chart.png"
                    },
                }
            ],
        ),
    )
    page = (
        await client.get(
            "/api/messages",
            params={"channel_id": BODY["channel_id"]},
        )
    ).json()
    assert page["messages"][0]["author_name"] == "Alpha KOL"
    assert page["messages"][0]["attachments"][0]["filename"] == "chart.png"
    assert page["messages"][0]["embeds"][0]["title"] == "Signal chart"


async def test_channel_groups_and_drag_layout_are_persisted(client):
    """验证分组增改删及频道拖拽位置以完整布局事务保存。"""
    first = (await client.post("/api/sources", json=BODY)).json()
    second_body = {**BODY, "name": "Second", "channel_id": "123456789012345679"}
    second = (await client.post("/api/sources", json=second_body)).json()
    group = (await client.post("/api/channel-groups", json={"name": "美股交易员"})).json()
    renamed = await client.put(f"/api/channel-groups/{group['id']}", json={"name": "VIP 美股"})
    assert renamed.json()["name"] == "VIP 美股"
    layout = {
        "groups": [{"group_id": group["id"], "position": 0}],
        "channels": [
            {"source_id": second["id"], "group_id": group["id"], "position": 0},
            {"source_id": first["id"], "group_id": group["id"], "position": 1},
        ],
    }
    assert (await client.put("/api/channel-layout", json=layout)).status_code == 204
    navigation = (await client.get("/api/messages/navigation")).json()
    assert navigation["groups"][0]["name"] == "VIP 美股"
    assert [item["name"] for item in navigation["groups"][0]["channels"]] == [
        "Second",
        "Trader A",
    ]
    assert navigation["ungrouped"] == []
    stale = {**layout, "channels": layout["channels"][:1]}
    assert (await client.put("/api/channel-layout", json=stale)).status_code == 409
    assert (await client.delete(f"/api/channel-groups/{group['id']}")).status_code == 204
    navigation = (await client.get("/api/messages/navigation")).json()
    assert navigation["groups"] == []
    assert len(navigation["ungrouped"]) == 2
