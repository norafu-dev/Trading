"""将 Discord 消息标准化为原始快照；保留引用和附件元数据，不解析交易。"""

import hashlib
import json
from datetime import datetime
from typing import Any

import discord
from pydantic import AwareDatetime, BaseModel, Field

from trading.config import Snowflake


class MessageSnapshot(BaseModel):
    """Observed Discord content, not a trading signal. Snowflakes remain strings."""

    message_id: Snowflake
    guild_id: Snowflake | None
    channel_id: Snowflake
    thread_id: Snowflake | None
    parent_channel_id: Snowflake | None
    author_id: Snowflake
    content: str
    author_name: str | None = None
    author_avatar_url: str | None = None
    channel_name: str | None = None
    created_at: AwareDatetime
    edited_at: AwareDatetime | None = None
    reply_to_message_id: Snowflake | None = None
    reply_to_channel_id: Snowflake | None = None
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    embeds: list[dict[str, Any]] = Field(default_factory=list)
    message_type: int = 0

    @property
    def version_at(self) -> datetime:
        """使用编辑时间或创建时间排序快照，防止旧内容覆盖新内容。"""
        return self.edited_at or self.created_at

    @property
    def fingerprint(self) -> str:
        """对规范化 JSON 计算稳定指纹，使重复收到的同一快照可以去重。"""
        payload = json.dumps(
            self.model_dump(
                mode="json", exclude={"author_name", "author_avatar_url", "channel_name"}
            ),
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode()).hexdigest()


def normalize_message(message: discord.Message) -> MessageSnapshot:
    """保留消息原文、字符串 ID、引用与附件元数据，转换成可持久化快照。"""
    is_thread = isinstance(message.channel, discord.Thread)
    reference = message.reference
    avatar = getattr(message.author, "display_avatar", None)
    return MessageSnapshot(
        message_id=str(message.id),
        guild_id=str(message.guild.id) if message.guild else None,
        channel_id=str(message.channel.id),
        thread_id=str(message.channel.id) if is_thread else None,
        parent_channel_id=str(message.channel.parent_id) if is_thread else None,
        author_id=str(message.author.id),
        content=message.content,
        author_name=getattr(message.author, "display_name", None),
        author_avatar_url=str(avatar.url) if avatar else None,
        channel_name=getattr(message.channel, "name", None),
        created_at=message.created_at,
        edited_at=message.edited_at,
        reply_to_message_id=(
            str(reference.message_id) if reference and reference.message_id else None
        ),
        reply_to_channel_id=(
            str(reference.channel_id) if reference and reference.channel_id else None
        ),
        attachments=[
            {
                "id": str(a.id),
                "filename": a.filename,
                "size": a.size,
                "content_type": a.content_type,
                "url": a.url,
                "proxy_url": a.proxy_url,
            }
            for a in message.attachments
        ],
        embeds=[e.to_dict() for e in message.embeds],
        message_type=message.type.value,
    )
