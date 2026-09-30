"""按频道 ID、原消息月份及真实图片类型生成对象键，避免跨频道共享文件。"""

import re
from datetime import datetime
from zoneinfo import ZoneInfo

MEDIA_MONTH_TIMEZONE = ZoneInfo("Asia/Tokyo")
LEGACY_PREFIX = "discord-images/v1/"
IMAGE_SUFFIXES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/avif": "avif",
}


def image_object_key(
    channel_id: str, message_created_at: datetime, digest: str, content_type: str
) -> str:
    """以原消息的日本本地月份分目录，同频道同月相同字节复用一个文件。"""
    month = message_created_at.astimezone(MEDIA_MONTH_TIMEZONE).strftime("%Y-%m")
    return f"discord-images/{channel_id}/{month}/{digest}.{IMAGE_SUFFIXES[content_type]}"


def is_legacy_key(key: str) -> bool:
    """只识别旧版由本项目生成的哈希键，不把桶内其他文件当作清理目标。"""
    match = re.fullmatch(r"discord-images/v1/([0-9a-f]{2})/([0-9a-f]{64})", key)
    return bool(match and match[1] == match[2][:2])
