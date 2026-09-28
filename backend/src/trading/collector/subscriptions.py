"""校验频道权限并订阅消息，按配置版本缓存结果以隔离失败来源。"""

from dataclasses import dataclass
from datetime import UTC, datetime

import discord
from sqlalchemy.ext.asyncio import AsyncEngine

from trading.config import Source, Sources
from trading.db.control import add_event, enabled_sources, mark_source
from trading.schemas import SourceDetails

VALIDATION_RETRY_SECONDS = 30


@dataclass(frozen=True)
class ValidationResult:
    configuration_updated_at: datetime
    is_accessible: bool
    checked_at: datetime

    def can_reuse(self, source: SourceDetails, now: datetime) -> bool:
        """配置未变时复用成功结果；失败结果只在重试间隔内复用。"""
        if self.configuration_updated_at != source.updated_at:
            return False
        return (
            self.is_accessible or (now - self.checked_at).total_seconds() < VALIDATION_RETRY_SECONDS
        )


class SourceSubscriptions:
    """Refresh configured sources, isolating inaccessible channels from valid ones."""

    def __init__(self, engine: AsyncEngine, client: discord.Client) -> None:
        """初始化频道校验缓存及其数据库和 Discord 客户端依赖。"""
        self.engine = engine
        self.client = client
        self.validated: dict[str, ValidationResult] = {}

    def clear(self) -> None:
        """连接状态变化后丢弃频道校验缓存，使下一轮同步重新检查权限。"""
        self.validated.clear()

    async def refresh(self) -> Sources:
        """读取启用配置，按需重新校验；只返回可用来源并淘汰停用来源的缓存。"""
        configured_sources = await enabled_sources(self.engine)
        now = datetime.now(UTC)
        accepted: list[Source] = []
        for source in configured_sources:
            previous = self.validated.get(source.id)
            if previous and previous.can_reuse(source, now):
                is_accessible = previous.is_accessible
            else:
                error = await self.validate_channel(source.channel_id)
                is_accessible = error is None
                await mark_source(self.engine, source, error)
                self.validated[source.id] = ValidationResult(source.updated_at, is_accessible, now)
                if error and (not previous or previous.is_accessible):
                    await add_event(self.engine, f"来源 {source.channel_id}：{error}", "warning")
            if is_accessible:
                accepted.append(
                    Source(
                        name=source.name, channel_id=source.channel_id, author_ids=source.author_ids
                    )
                )
        enabled_ids = {source.id for source in configured_sources}
        self.validated = {
            source_id: result
            for source_id, result in self.validated.items()
            if source_id in enabled_ids
        }
        return Sources(sources=accepted)

    async def validate_channel(self, channel_id: str) -> str | None:
        """确认指定位置是可访问的文本频道或 Thread 并订阅；返回可展示的失败原因。"""
        try:
            channel = self.client.get_channel(int(channel_id)) or await self.client.fetch_channel(
                int(channel_id)
            )
            if not isinstance(channel, (discord.TextChannel, discord.Thread)):
                return "请填写文本频道或具体 Thread 的 ID"
            await channel.guild.subscribe()
        except discord.Forbidden:
            return "当前 Discord 账号无权访问此频道"
        except discord.NotFound:
            return "频道不存在或当前账号不可见，请检查 ID"
        except (discord.HTTPException, OSError, TimeoutError):
            return "Discord 请求失败，将自动重试"
        return None
