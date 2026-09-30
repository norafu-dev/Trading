"""验证图片任务事务、跨消息内容去重、重启恢复、历史补建及安全媒体接口。"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from sqlalchemy import delete, func, select, update

from trading.api import create_app
from trading.collector.messages import MessageSnapshot
from trading.config import Settings
from trading.db.media import (
    claim_image,
    fail_image,
    finish_image,
    retry_failed_images,
    seed_historical_images,
    storage_summary,
)
from trading.db.message_browser import channel_messages
from trading.db.models import MediaArchive, Message, MessageVersion
from trading.db.repository import store_snapshot
from trading.media.worker import ImageArchiveError, MediaArchiver

pytestmark = pytest.mark.integration
URL = "https://cdn.discordapp.com/attachments/20/40/chart.png?ex=111&is=222&hm=333"


def image_snapshot(message_id="100"):
    """构造带一张图片及 Embed 的消息，不包含真实频道或凭证。"""
    return MessageSnapshot(
        message_id=message_id,
        guild_id=None,
        channel_id="20",
        thread_id=None,
        parent_channel_id=None,
        author_id="30",
        content="图片信号",
        created_at=datetime(2026, 9, 17, tzinfo=UTC),
        attachments=[
            {"id": "40", "filename": "chart.png", "url": URL, "content_type": "image/png"}
        ],
        embeds=[{"description": "原文", "image": {"url": URL}}],
    )


async def test_media_queue_is_transactional_and_idempotent(engine, monkeypatch):
    """验证重复投递只建一个任务，任务写入失败时消息与版本也整体回滚。"""
    await store_snapshot(engine, image_snapshot())
    await store_snapshot(engine, image_snapshot())
    async with engine.connect() as connection:
        assert await connection.scalar(select(func.count()).select_from(MediaArchive)) == 1
    monkeypatch.setattr(
        "trading.db.repository.enqueue_images", AsyncMock(side_effect=RuntimeError("failed"))
    )
    with pytest.raises(RuntimeError):
        await store_snapshot(engine, image_snapshot("101"))
    async with engine.connect() as connection:
        assert await connection.scalar(select(func.count()).select_from(Message)) == 1
        assert await connection.scalar(select(func.count()).select_from(MessageVersion)) == 1


async def test_worker_deduplicates_original_bytes_and_leaves_snapshots_unchanged(
    engine, monkeypatch
):
    """不同消息中的相同字节只上传一次，快照仍保留原始 Discord URL。"""
    await store_snapshot(engine, image_snapshot())
    await store_snapshot(engine, image_snapshot("101"))
    download = AsyncMock(return_value=(b"original-image-bytes", "image/png"))
    monkeypatch.setattr("trading.media.worker.download_image", download)
    storage = SimpleNamespace(upload=AsyncMock())
    worker = MediaArchiver(engine, SimpleNamespace(), Settings())
    await worker.archive(await claim_image(engine), None, storage)
    await worker.archive(await claim_image(engine), None, storage)
    assert storage.upload.await_count == 1
    summary = await storage_summary(engine, True, 1)
    assert summary["object_count"] == 1
    assert summary["size_bytes"] == len(b"original-image-bytes")
    assert summary["stored"] == 2 and summary["capacity_warning"]
    async with engine.connect() as connection:
        raw = await connection.scalar(select(Message.snapshot).where(Message.message_id == "100"))
        assert raw["attachments"][0]["url"] == URL
        assert await connection.scalar(select(func.count()).select_from(MessageVersion)) == 2
    page = await channel_messages(engine, "20", None, 50)
    assert page.messages[0].attachments[0].url.startswith("/api/media/")
    assert page.messages[0].embeds[0].image_url.startswith("/api/media/")


async def test_lease_recovery_and_stale_completion(engine):
    """未过期租约不能再领取；重启后过期任务可恢复，旧完成回调不能覆盖。"""
    await store_snapshot(engine, image_snapshot())
    original = await claim_image(engine)
    assert await claim_image(engine) is None
    async with engine.begin() as connection:
        await connection.execute(
            update(MediaArchive).values(lease_until=datetime.now(UTC) - timedelta(seconds=1))
        )
    recovered = await claim_image(engine)
    assert recovered["id"] == original["id"] and recovered["attempts"] == 2
    await finish_image(engine, original, "a" * 64, 20, "image/png")
    async with engine.connect() as connection:
        assert await connection.scalar(select(MediaArchive.status)) == "processing"
    await finish_image(engine, recovered, "a" * 64, 20, "image/png")
    assert await claim_image(engine) is None


async def test_failed_retry_and_backoff(engine):
    """暂时失败留存未来重试时间，达到上限后停止，手动重试清零次数。"""
    await store_snapshot(engine, image_snapshot())
    first = await claim_image(engine)
    await fail_image(engine, first, "temporary")
    assert await claim_image(engine) is None
    async with engine.begin() as connection:
        await connection.execute(
            update(MediaArchive).values(attempts=4, next_attempt_at=datetime.now(UTC))
        )
    fifth = await claim_image(engine)
    await fail_image(engine, fifth, "temporary")
    assert (await storage_summary(engine, True, 100))["failed"] == 1
    assert await retry_failed_images(engine) == 1
    next_job = await claim_image(engine)
    assert next_job["attempts"] == 1


async def test_historical_seed_preserves_changed_image_versions(engine):
    """旧版与新版图片都补建任务，不用新版图片替代历史图片。"""
    first = image_snapshot()
    await store_snapshot(engine, first)
    newer = first.model_copy(
        update={
            "edited_at": first.created_at + timedelta(minutes=1),
            "attachments": [
                {"id": "41", "filename": "new.png", "url": URL.replace("/40/", "/41/")}
            ],
            "embeds": [],
        }
    )
    await store_snapshot(engine, newer)
    async with engine.begin() as connection:
        await connection.execute(delete(MediaArchive))
    await seed_historical_images(engine)
    await seed_historical_images(engine)
    async with engine.connect() as connection:
        assert await connection.scalar(select(func.count()).select_from(MediaArchive)) == 2


async def test_expired_link_refresh_does_not_create_new_message_version(engine, monkeypatch):
    """过期后只刷新下载地址，不重存消息快照或生成伪消息版本。"""
    await store_snapshot(engine, image_snapshot())
    download = AsyncMock(
        side_effect=[ImageArchiveError("expired", refresh=True), (b"png", "image/png")]
    )
    monkeypatch.setattr("trading.media.worker.download_image", download)
    worker = MediaArchiver(engine, SimpleNamespace(), Settings())
    refresh = AsyncMock(return_value=URL.replace("ex=111", "ex=999"))
    monkeypatch.setattr(worker, "refreshed_url", refresh)
    await worker.process(await claim_image(engine), None, SimpleNamespace(upload=AsyncMock()))
    assert download.await_count == 2 and refresh.await_count == 1
    async with engine.connect() as connection:
        assert await connection.scalar(select(func.count()).select_from(MessageVersion)) == 1


async def test_missing_image_is_terminal_and_upload_failure_is_retryable(engine, monkeypatch):
    """删除的图片不无限抓取；R2 暂时失败仍保留待重试任务。"""
    await store_snapshot(engine, image_snapshot())
    worker = MediaArchiver(engine, SimpleNamespace(), Settings())
    monkeypatch.setattr(
        worker, "archive", AsyncMock(side_effect=ImageArchiveError("deleted", terminal=True))
    )
    await worker.process(await claim_image(engine), None, None)
    assert (await storage_summary(engine, True, 100))["failed"] == 1
    await retry_failed_images(engine)
    from botocore.exceptions import ClientError

    monkeypatch.setattr(
        worker,
        "archive",
        AsyncMock(side_effect=ClientError({"Error": {"Code": "AccessDenied"}}, "PutObject")),
    )
    await worker.process(await claim_image(engine), None, None)
    summary = await storage_summary(engine, True, 100)
    assert summary["pending"] == 1 and "R2" in summary["last_error"]


async def test_private_media_api_and_unconfigured_retry(engine, monkeypatch):
    """未配置拒绝重试；已归档图片通过新签名跳转，不暴露密钥或原始 URL。"""
    await store_snapshot(engine, image_snapshot())
    job = await claim_image(engine)
    await finish_image(engine, job, "b" * 64, 20, "image/png")
    app = create_app()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            headers={"X-Requested-With": "trading-panel"},
        ) as client:
            assert (await client.post("/api/media/retry")).status_code == 409
            assert (await client.get(f"/api/media/{job['id']}")).status_code == 503
            storage = SimpleNamespace(
                read_url=MagicMock(return_value="https://example.com/signed"), close=MagicMock()
            )
            # 假存储只验证接口契约；测试没有真正连接 R2。
            monkeypatch.setattr(app.state, "storage", storage)
            response = await client.get(f"/api/media/{job['id']}")
            assert response.status_code == 307
            assert response.headers["location"] == "https://example.com/signed"
            assert response.headers["cache-control"] == "no-store"
            assert (await client.get("/api/media/not-a-uuid")).status_code == 422


async def test_repeated_crashes_eventually_stop_and_concurrent_claims_do_not_overlap(engine):
    """并发消费者不会领取同一任务，反复中断也不能越过重试上限。"""
    import asyncio

    await store_snapshot(engine, image_snapshot())
    jobs = await asyncio.gather(claim_image(engine), claim_image(engine))
    assert sum(job is not None for job in jobs) == 1
    async with engine.begin() as connection:
        await connection.execute(
            update(MediaArchive).values(
                attempts=5, lease_until=datetime.now(UTC) - timedelta(seconds=1)
            )
        )
    assert await claim_image(engine) is None
    assert (await storage_summary(engine, True, 100))["failed"] == 1


async def test_refresh_matches_same_image_and_rejects_replaced_image(engine):
    """通过 Discord 客户端读取原消息，签名改变仍可匹配，换图后必须失败。"""
    import discord

    original = image_snapshot()
    channel = MagicMock(spec=discord.TextChannel)
    attachment = SimpleNamespace(
        id=40,
        filename="chart.png",
        size=100,
        content_type="image/png",
        url=URL.replace("ex=111", "ex=999"),
        proxy_url=URL,
    )
    message = SimpleNamespace(
        id=100,
        guild=None,
        channel=channel,
        author=SimpleNamespace(id=30, display_name="Trader", display_avatar=None),
        content=original.content,
        created_at=original.created_at,
        edited_at=None,
        reference=None,
        attachments=[attachment],
        embeds=[],
        type=SimpleNamespace(value=0),
    )
    channel.id = 20
    channel.name = "channel"
    channel.fetch_message = AsyncMock(return_value=message)
    client = SimpleNamespace(get_channel=MagicMock(return_value=channel))
    await store_snapshot(engine, original)
    job = await claim_image(engine)
    worker = MediaArchiver(engine, client, Settings())
    assert await worker.refreshed_url(job) == attachment.url
    attachment.id = 41
    attachment.url = URL.replace("/40/", "/41/")
    attachment.proxy_url = attachment.url
    with pytest.raises(ImageArchiveError, match="更换"):
        await worker.refreshed_url(job)


async def test_unexpected_image_error_is_visible_and_retryable(engine, monkeypatch):
    """格式识别等意外程序错误也写入状态，不永久挂在处理中。"""
    await store_snapshot(engine, image_snapshot())
    worker = MediaArchiver(engine, SimpleNamespace(), Settings())
    monkeypatch.setattr(worker, "archive", AsyncMock(side_effect=TypeError("private-data")))
    await worker.process(await claim_image(engine), None, None)
    summary = await storage_summary(engine, True, 100)
    assert summary["processing"] == 0 and summary["pending"] == 1
    assert "TypeError" in summary["last_error"] and "private-data" not in summary["last_error"]


async def test_same_image_in_different_channels_or_months_has_own_object(engine, monkeypatch):
    """即使相同字节出现在不同频道/月，也各自存入所属目录，页面引用不会串频道。"""
    original = image_snapshot()
    other_channel = original.model_copy(update={"message_id": "101", "channel_id": "21"})
    other_month = original.model_copy(
        update={"message_id": "102", "created_at": datetime(2026, 10, 1, tzinfo=UTC)}
    )
    for snapshot in (original, other_channel, other_month):
        await store_snapshot(engine, snapshot)
    monkeypatch.setattr(
        "trading.media.worker.download_image", AsyncMock(return_value=(b"same-bytes", "image/png"))
    )
    storage = SimpleNamespace(upload=AsyncMock())
    worker = MediaArchiver(engine, SimpleNamespace(), Settings())
    for _ in range(3):
        await worker.archive(await claim_image(engine), None, storage)
    assert storage.upload.await_count == 3
    keys = {call.args[0] for call in storage.upload.await_args_list}
    assert len(keys) == 3
    assert any(key.startswith("discord-images/21/2026-09/") for key in keys)
    summary = await storage_summary(engine, True, 100)
    assert summary["object_count"] == 3 and summary["size_bytes"] == 3 * len(b"same-bytes")
