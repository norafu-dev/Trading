"""查询扁平频道导航、展示媒体与分页消息；不向 Discord 发起历史抓取。"""

from urllib.parse import urlparse

from sqlalchemy import Numeric, cast, func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from trading.db.models import ChannelGroup, ChannelSource, Message
from trading.schemas import (
    CollectedMessage,
    MessageChannel,
    MessageEmbed,
    MessageEmbedField,
    MessageGroup,
    MessageMedia,
    MessageNavigation,
    MessagePage,
)


def discord_media_url(value: object) -> str | None:
    """只返回 Discord CDN 或代理域名的 HTTPS 媒体地址。"""
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    if parsed.scheme == "https" and parsed.netloc in {
        "cdn.discordapp.com",
        "media.discordapp.net",
        "images-ext-1.discordapp.net",
        "images-ext-2.discordapp.net",
    }:
        return value
    return None


def visible_attachments(snapshot: dict) -> list[MessageMedia]:
    """从原始快照提取可安全打开的附件，过滤缺少文件名或 Discord 地址的条目。"""
    result = []
    for attachment in snapshot.get("attachments", []):
        if not isinstance(attachment, dict):
            continue
        url = discord_media_url(attachment.get("url")) or discord_media_url(
            attachment.get("proxy_url")
        )
        filename = attachment.get("filename")
        if url and isinstance(filename, str):
            result.append(
                MessageMedia(
                    filename=filename,
                    url=url,
                    content_type=(
                        attachment.get("content_type")
                        if isinstance(attachment.get("content_type"), str)
                        else None
                    ),
                )
            )
    return result


def visible_embeds(snapshot: dict) -> list[MessageEmbed]:
    """提取 Embed 文本、字段、页脚与 Discord 代理图片。"""
    result = []
    for embed in snapshot.get("embeds", []):
        if not isinstance(embed, dict):
            continue
        image = embed.get("image") if isinstance(embed.get("image"), dict) else {}
        thumbnail = embed.get("thumbnail") if isinstance(embed.get("thumbnail"), dict) else {}
        image_url = (
            discord_media_url(image.get("proxy_url"))
            or discord_media_url(image.get("url"))
            or discord_media_url(thumbnail.get("proxy_url"))
            or discord_media_url(thumbnail.get("url"))
        )
        title = embed.get("title") if isinstance(embed.get("title"), str) else None
        description = (
            embed.get("description") if isinstance(embed.get("description"), str) else None
        )
        fields = [
            MessageEmbedField(
                name=field["name"], value=field["value"], inline=field.get("inline") is True
            )
            for field in embed.get("fields", [])
            if isinstance(field, dict)
            and isinstance(field.get("name"), str)
            and isinstance(field.get("value"), str)
        ]
        footer_data = embed.get("footer") if isinstance(embed.get("footer"), dict) else {}
        footer = footer_data.get("text") if isinstance(footer_data.get("text"), str) else None
        timestamp = embed.get("timestamp") if isinstance(embed.get("timestamp"), str) else None
        color_value = embed.get("color")
        color = (
            f"#{color_value:06x}"
            if isinstance(color_value, int) and 0 <= color_value <= 0xFFFFFF
            else None
        )
        if image_url or title or description or fields or footer:
            result.append(
                MessageEmbed(
                    title=title,
                    description=description,
                    image_url=image_url,
                    fields=fields,
                    footer=footer,
                    timestamp=timestamp,
                    color=color,
                )
            )
    return result


async def message_navigation(engine: AsyncEngine) -> MessageNavigation:
    """合并当前来源与留存频道，按用户分组和拖拽位置生成单层频道列表。"""
    async with engine.connect() as connection:
        sources = (await connection.execute(select(ChannelSource.__table__))).mappings().all()
        groups = (await connection.execute(select(ChannelGroup.__table__))).mappings().all()
        counts = (
            (
                await connection.execute(
                    select(Message.channel_id, func.count().label("total")).group_by(
                        Message.channel_id
                    )
                )
            )
            .mappings()
            .all()
        )
        profiles = (
            (
                await connection.execute(
                    select(
                        Message.channel_id,
                        Message.created_at,
                        Message.snapshot["channel_name"].astext.label("channel_name"),
                    )
                    .distinct(Message.channel_id)
                    .order_by(
                        Message.channel_id,
                        Message.created_at.desc(),
                        cast(Message.message_id, Numeric).desc(),
                    )
                )
            )
            .mappings()
            .all()
        )
    totals = {row["channel_id"]: row["total"] for row in counts}
    channel_names = {row["channel_id"]: row["channel_name"] for row in profiles}
    configured_ids = {source["channel_id"] for source in sources}
    channels = [
        MessageChannel(
            channel_id=source["channel_id"],
            source_id=source["id"],
            group_id=source["group_id"],
            position=source["position"],
            name=source["name"],
            enabled=source["enabled"],
            message_count=totals.get(source["channel_id"], 0),
        )
        for source in sources
    ]
    channels.extend(
        MessageChannel(
            channel_id=channel_id,
            name=channel_names.get(channel_id) or channel_id,
            archived=True,
            message_count=total,
        )
        for channel_id, total in totals.items()
        if channel_id not in configured_ids
    )
    grouped_channels = {
        group["id"]: sorted(
            (channel for channel in channels if channel.group_id == group["id"]),
            key=lambda channel: (channel.position, channel.name.lower()),
        )
        for group in groups
    }
    navigation_groups = [
        MessageGroup(
            id=group["id"],
            name=group["name"],
            position=group["position"],
            channels=grouped_channels[group["id"]],
        )
        for group in sorted(groups, key=lambda row: (row["position"], row["name"].lower()))
    ]
    ungrouped = sorted(
        (channel for channel in channels if channel.group_id is None),
        key=lambda channel: (channel.position, channel.name.lower()),
    )
    return MessageNavigation(groups=navigation_groups, ungrouped=ungrouped)


async def channel_messages(
    engine: AsyncEngine, channel_id: str, before: str | None, limit: int
) -> MessagePage:
    """读取频道内全部已配置作者消息，以数字 Snowflake 游标稳定向前翻页。"""
    message_order = cast(Message.message_id, Numeric)
    statement = select(Message.__table__).where(Message.channel_id == channel_id)
    if before is not None:
        statement = statement.where(message_order < int(before))
    statement = statement.order_by(message_order.desc()).limit(limit + 1)
    async with engine.connect() as connection:
        rows = (await connection.execute(statement)).mappings().all()
        source = (
            (
                await connection.execute(
                    select(ChannelSource.__table__).where(ChannelSource.channel_id == channel_id)
                )
            )
            .mappings()
            .first()
        )
    has_older = len(rows) > limit
    page = rows[:limit]
    messages = []
    for row in reversed(page):
        snapshot = row["snapshot"]
        configured_name = (
            source["kol_name"] if source and row["author_id"] in source["author_ids"] else None
        )
        messages.append(
            CollectedMessage(
                **{
                    key: row[key]
                    for key in (
                        "message_id",
                        "channel_id",
                        "author_id",
                        "content",
                        "created_at",
                        "first_seen_at",
                    )
                },
                author_name=configured_name or snapshot.get("author_name") or row["author_id"],
                reply_to_message_id=snapshot.get("reply_to_message_id"),
                attachments=visible_attachments(snapshot),
                embeds=visible_embeds(snapshot),
            )
        )
    return MessagePage(messages=messages, next_before=page[-1]["message_id"] if has_older else None)
