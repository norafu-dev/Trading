"""提取 Discord 图片与稳定标识，仅允许固定 CDN 域名，保留原始快照。"""

import hashlib
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

DISCORD_MEDIA_HOSTS = {
    "cdn.discordapp.com",
    "media.discordapp.net",
    "images-ext-1.discordapp.net",
    "images-ext-2.discordapp.net",
}
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif")


def discord_media_url(value: object) -> str | None:
    """校验下载边界，拒绝其他主机、端口、用户信息和非 HTTPS 链接。"""
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme == "https" and parsed.netloc in DISCORD_MEDIA_HOSTS:
            return value
    except ValueError:
        return None
    return None


def canonical_media_url(url: str) -> str:
    """移除 Discord 签名参数，保留会影响图片内容的尺寸和格式参数。"""
    parsed = urlsplit(url)
    query = urlencode(
        sorted((k, v) for k, v in parse_qsl(parsed.query) if k not in {"ex", "is", "hm"})
    )
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, ""))


def media_key(url: str) -> str:
    """为同一媒体链接生成稳定键，链接签名刷新不会创建重复任务。"""
    return hashlib.sha256(canonical_media_url(url).encode()).hexdigest()


@dataclass(frozen=True)
class ImageCandidate:
    """同一图片的稳定链接标识及下载地址，用于刷新原消息后的匹配。"""

    key: str
    url: str


def image_candidates(snapshot: dict) -> list[ImageCandidate]:
    """提取图片附件以及 Embed 大图和缩略图；不归档视频、文档或任意外链。"""
    result = []
    for attachment in snapshot.get("attachments", []):
        if not isinstance(attachment, dict):
            continue
        filename = str(attachment.get("filename", ""))
        content_type = str(attachment.get("content_type") or "")
        url = discord_media_url(attachment.get("url")) or discord_media_url(
            attachment.get("proxy_url")
        )
        if url and (
            content_type.startswith("image/") or filename.lower().endswith(IMAGE_EXTENSIONS)
        ):
            result.append(ImageCandidate(media_key(url), url))
    for embed in snapshot.get("embeds", []):
        if not isinstance(embed, dict):
            continue
        for kind in ("image", "thumbnail"):
            image = embed.get(kind)
            if not isinstance(image, dict):
                continue
            # 原图优先；外链原图只允许通过 Discord 提供的固定域名代理下载。
            url = discord_media_url(image.get("url")) or discord_media_url(image.get("proxy_url"))
            if url:
                result.append(ImageCandidate(media_key(url), url))
    return result


def image_content_type(data: bytes | bytearray) -> str | None:
    """根据文件签名识别可展示的位图，不把 HTML 错误页或 SVG 当图片上传。"""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:8] == b"ftyp" and data[8:12] in (b"avif", b"avis"):
        return "image/avif"
    return None
