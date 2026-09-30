"""管理面板的请求与响应契约，同时提供 Collector 使用的来源记录类型。"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from trading.config import Snowflake


class SourceInput(BaseModel):
    model_config = {"extra": "forbid", "str_strip_whitespace": True}
    name: str = Field(min_length=1, max_length=100)
    kol_name: str = Field(min_length=1, max_length=100)
    group_id: UUID | None = None
    position: int = Field(default=0, ge=0)
    channel_id: Snowflake
    author_ids: list[Snowflake] = Field(min_length=1, max_length=50)
    enabled: bool = True

    @field_validator("author_ids")
    @classmethod
    def deduplicate_authors(cls, values: list[str]) -> list[str]:
        """按输入顺序去重作者 ID，保证保存后的过滤规则没有重复项。"""
        return list(dict.fromkeys(values))


class SourceDetails(SourceInput):
    id: str
    status: str
    last_error: str | None
    checked_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RuntimeDetails(BaseModel):
    id: str
    state: str
    heartbeat_at: datetime | None
    started_at: datetime | None
    connected_at: datetime | None
    last_message_at: datetime | None
    last_saved_at: datetime | None
    source_sync_at: datetime | None
    active_sources: int
    last_error: str | None


class RuntimeStatus(RuntimeDetails):
    process_alive: bool
    heartbeat_age_seconds: float | None


class MessageSummary(BaseModel):
    message_id: str
    channel_id: str
    author_id: str
    content: str
    created_at: datetime
    first_seen_at: datetime


class EventSummary(BaseModel):
    id: str
    level: str
    message: str
    occurred_at: datetime


class StorageSummary(BaseModel):
    """本项目确认归档的容量及任务状态，不代表整个 Cloudflare 账户账单。"""

    configured: bool
    object_count: int
    size_bytes: int
    warning_bytes: int
    capacity_warning: bool
    pending: int
    processing: int
    stored: int
    failed: int
    last_error: str | None


class DashboardResponse(BaseModel):
    storage: StorageSummary
    sources: list[SourceDetails]
    runtime: RuntimeStatus
    total_messages: int
    messages: list[MessageSummary]
    events: list[EventSummary]
    server_time: datetime
    checkpoints: list["CheckpointDetails"] = Field(default_factory=list)


class CheckpointDetails(BaseModel):
    """每个频道的补采覆盖起点、进度与失败重试状态，不代表全量 Discord 历史。"""

    channel_id: str
    name: str
    cursor_id: str
    target_id: str | None
    coverage_started_at: datetime
    state: str
    attempts: int
    next_attempt_at: datetime
    last_error: str | None
    last_completed_at: datetime | None


class MessageChannel(BaseModel):
    """左侧一行频道入口；来源删除后仍可作为未分组历史频道显示。"""

    channel_id: str
    source_id: str | None = None
    group_id: str | None = None
    position: int = 0
    name: str
    enabled: bool = False
    archived: bool = False
    message_count: int = 0


class MessageGroup(BaseModel):
    """用户创建的频道分组，顺序和频道归属可由拖拽更新。"""

    id: str
    name: str
    position: int
    channels: list[MessageChannel]


class MessageNavigation(BaseModel):
    """扁平频道导航，按自定义分组组织并保留未分组入口。"""

    groups: list[MessageGroup]
    ungrouped: list[MessageChannel]


class ChannelGroupInput(BaseModel):
    """新增或重命名频道分组的输入。"""

    model_config = {"extra": "forbid", "str_strip_whitespace": True}
    name: str = Field(min_length=1, max_length=100)


class ChannelGroupDetails(ChannelGroupInput):
    """已经保存的频道分组及其排序位置。"""

    id: str
    position: int


class ChannelPosition(BaseModel):
    """一条来源在分组中的目标位置。"""

    source_id: UUID
    group_id: UUID | None = None
    position: int = Field(ge=0)


class GroupPosition(BaseModel):
    """一个分组的目标位置。"""

    group_id: UUID
    position: int = Field(ge=0)


class ChannelLayoutInput(BaseModel):
    """一次拖拽后的完整频道和分组顺序，用单个事务保存。"""

    model_config = {"extra": "forbid"}
    groups: list[GroupPosition]
    channels: list[ChannelPosition]


class MessageMedia(BaseModel):
    """可在浏览器安全显示的 Discord 附件；非图片附件仍保留文件名和链接。"""

    filename: str
    url: str
    content_type: str | None = None
    archive_status: str | None = None
    archive_error: str | None = None


class MessageEmbedField(BaseModel):
    """Embed 内一项命名字段；inline 只影响桌面排版。"""

    name: str
    value: str
    inline: bool = False


class MessageEmbed(BaseModel):
    """Discord Embed 的文本、字段、页脚与代理图片。"""

    title: str | None = None
    description: str | None = None
    url: str | None = None
    image_url: str | None = None
    archive_status: str | None = None
    archive_error: str | None = None
    fields: list[MessageEmbedField] = Field(default_factory=list)
    footer: str | None = None
    timestamp: datetime | None = None
    color: str | None = None


class CollectedMessage(MessageSummary):
    """消息正文及展示资料；旧快照缺失资料时允许使用 ID 占位。"""

    author_name: str | None = None
    reply_to_message_id: str | None = None
    attachments: list[MessageMedia] = Field(default_factory=list)
    embeds: list[MessageEmbed] = Field(default_factory=list)
    first_delivery: str = "unknown"
    collection_delay_seconds: float = 0
    edited_at: datetime | None = None
    deleted_at: datetime | None = None
    is_stale: bool = True
    freshness_seconds: int = 120


class MessagePage(BaseModel):
    """选定频道的一页消息，包含频道内各作者并按时间从旧到新返回。"""

    messages: list[CollectedMessage]
    next_before: str | None = None
