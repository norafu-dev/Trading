"""验证图片下载边界、签名刷新标识和类型识别，不需要外部 Discord/R2。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from trading.config import Settings
from trading.media.candidates import (
    discord_media_url,
    image_candidates,
    image_content_type,
    media_key,
)
from trading.media.worker import ImageArchiveError, download_image


@pytest.mark.parametrize(
    "url",
    [
        "http://cdn.discordapp.com/a.png",
        "https://localhost/a.png",
        "https://cdn.discordapp.com.evil.example/a.png",
        "https://cdn.discordapp.com:443/a.png",
        "https://user@cdn.discordapp.com/a.png",
        "http://169.254.169.254/",
        "https://[bad",
    ],
)
def test_media_url_rejects_untrusted_targets(url):
    """下载仅限固定 HTTPS CDN 域名，拒绝内部地址和伪装主机。"""
    assert discord_media_url(url) is None


def test_signature_refresh_is_stable_but_transforms_and_new_images_differ():
    """URL 签名变化不生成新任务，但不同图片和内容转换保留不同标识。"""
    base = "https://cdn.discordapp.com/attachments/1/2/a.png"
    assert media_key(base + "?ex=1&is=2&hm=3") == media_key(base + "?ex=4&is=5&hm=6")
    assert media_key(base + "?width=100") != media_key(base + "?width=200")
    assert media_key(base) != media_key(base.replace("a.png", "b.png"))


def test_embed_external_images_use_only_discord_proxy():
    """外部 Embed 使用 Discord 代理，大图与缩略图都提取，文档不归档。"""
    snapshot = {
        "attachments": [{"filename": "readme.txt", "url": "https://cdn.discordapp.com/readme.txt"}],
        "embeds": [
            {
                "image": {
                    "url": "https://example.com/a.png",
                    "proxy_url": "https://images-ext-1.discordapp.net/external/a.png",
                },
                "thumbnail": {"url": "https://cdn.discordapp.com/b.png"},
            }
        ],
    }
    images = image_candidates(snapshot)
    assert len(images) == 2
    assert images[0].url.startswith("https://images-ext-1.discordapp.net/")


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"\x89PNG\r\n\x1a\nabc", "image/png"),
        (b"\xff\xd8\xffabc", "image/jpeg"),
        (b"GIF89aabc", "image/gif"),
        (b"RIFFxxxxWEBP", "image/webp"),
        (b"xxxxftypavif", "image/avif"),
        (b"<html>403</html>", None),
        (b"<svg/>", None),
    ],
)
def test_image_magic_rejects_error_pages_and_active_content(data, expected):
    """根据字节而非文件后缀区分位图、CDN 错误页和 SVG。"""
    assert image_content_type(data) == expected
    assert image_content_type(bytearray(data)) == expected


async def test_download_limit_and_redirect_rejection():
    """超出限制和 HTTP 重定向都被拒绝，下载不继续访问重定向目标。"""
    session = MagicMock()
    response = SimpleNamespace(status=302, content_length=None)
    context = session.get.return_value
    context.__aenter__ = AsyncMock(return_value=response)
    context.__aexit__ = AsyncMock(return_value=False)
    url = "https://cdn.discordapp.com/a.png"
    with pytest.raises(ImageArchiveError):
        await download_image(session, url, 10)
    session.get.assert_called_once_with(url, allow_redirects=False)
    response.status = 200
    response.content_length = 11
    with pytest.raises(ImageArchiveError, match="上限"):
        await download_image(session, url, 10)


def test_r2_configuration_masks_both_keys():
    """配置展示隐藏 S3 密钥，字段不完整时不能误报归档可运行。"""
    settings = Settings(
        r2_account_id="a" * 32,
        r2_bucket="test-bucket",
        r2_access_key_id="fake-access",
        r2_secret_access_key="fake-secret",
    )
    assert settings.r2_configured
    assert "fake-access" not in repr(settings) and "fake-secret" not in repr(settings)
    assert not Settings(r2_bucket="test-bucket").r2_configured


async def test_stream_limit_without_content_length_and_preserves_bytes():
    """没有长度头时仍限制流式字节数；成功时不转码或压缩图片内容。"""
    chunks = [b"\x89PNG\r\n\x1a\n", b"original"]

    async def stream(chunk_size):
        """模拟逐块下载响应，验证真实累积路径。"""
        for chunk in chunks:
            yield chunk

    session = MagicMock()
    response = SimpleNamespace(
        status=200, content_length=None, content=SimpleNamespace(iter_chunked=stream)
    )
    session.get.return_value.__aenter__ = AsyncMock(return_value=response)
    session.get.return_value.__aexit__ = AsyncMock(return_value=False)
    url = "https://cdn.discordapp.com/a.png"
    with pytest.raises(ImageArchiveError, match="上限"):
        await download_image(session, url, 10)
    data, content_type = await download_image(session, url, 100)
    assert data == b"".join(chunks) and content_type == "image/png"


async def test_r2_sdk_upload_and_presigned_get_contract():
    """用 SDK Stub 验证对象键与原始字节上传，签名 GET 不需要访问远端。"""
    from urllib.parse import parse_qs, urlsplit

    from botocore.stub import Stubber

    from trading.media.storage import R2Storage

    settings = Settings(
        r2_account_id="a" * 32,
        r2_bucket="test-bucket",
        r2_access_key_id="fake-access",
        r2_secret_access_key="fake-secret",
    )
    storage = R2Storage(settings)
    digest = "a" * 64
    key = f"discord-images/20/2026-09/{digest}.png"
    try:
        with Stubber(storage.client) as stub:
            stub.add_response(
                "put_object",
                {"ETag": '"test"'},
                {
                    "Bucket": "test-bucket",
                    "Key": key,
                    "Body": b"original",
                    "ContentType": "image/png",
                    "CacheControl": "private, max-age=3600",
                },
            )
            await storage.upload(key, b"original", "image/png")
            stub.assert_no_pending_responses()
        url = urlsplit(storage.read_url(key))
        assert url.scheme == "https"
        assert url.hostname == f"{'a' * 32}.r2.cloudflarestorage.com"
        assert parse_qs(url.query)["X-Amz-Expires"] == ["3600"]
    finally:
        storage.close()


def test_channel_month_paths_are_independent_and_use_message_local_month():
    """不同频道/月不共享文件，UTC 月末按项目日本时区归入正确月份。"""
    from datetime import UTC, datetime

    from trading.media.layout import image_object_key, is_legacy_key

    digest = "a" * 64
    utc_date = datetime(2026, 9, 30, 16, tzinfo=UTC)
    first = image_object_key("20", utc_date, digest, "image/png")
    assert first == f"discord-images/20/2026-10/{digest}.png"
    assert image_object_key("21", utc_date, digest, "image/png") != first
    assert is_legacy_key(f"discord-images/v1/aa/{digest}")
    assert not is_legacy_key(first)
    assert not is_legacy_key(f"discord-images/v1/bb/{digest}")


async def test_copy_verification_failure_never_deletes_source():
    """复制返回错误内容时校验失败，旧源对象不被删除。"""
    from io import BytesIO

    from botocore.response import StreamingBody

    from trading.media.storage import R2Storage

    settings = Settings(
        r2_account_id="a" * 32,
        r2_bucket="test-bucket",
        r2_access_key_id="fake-access",
        r2_secret_access_key="fake-secret",
    )
    storage = R2Storage(settings)
    client = MagicMock()
    storage.client.close()
    storage.client = client
    client.get_object.return_value = {"Body": StreamingBody(BytesIO(b"wrong"), 5)}
    try:
        with pytest.raises(ValueError, match="verification"):
            await storage.copy_verified(
                f"discord-images/v1/aa/{'a' * 64}",
                f"discord-images/20/2026-09/{'a' * 64}.png",
                "a" * 64,
                5,
            )
        client.delete_object.assert_not_called()
        with pytest.raises(ValueError, match="Refusing"):
            await storage.delete_legacy("discord-images/20/2026-09/image.png")
    finally:
        storage.close()
