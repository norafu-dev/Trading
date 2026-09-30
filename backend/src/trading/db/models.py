"""声明 PostgreSQL 表、索引和幂等约束；实际建表由 Alembic 迁移完成。"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_channel_created", "channel_id", "created_at"),
        Index("ix_messages_author_created", "author_id", "created_at"),
    )
    message_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    channel_id: Mapped[str] = mapped_column(String(20))
    author_id: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    version_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)


class MessageVersion(Base):
    __tablename__ = "message_versions"
    message_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("messages.message_id"), primary_key=True
    )
    fingerprint: Mapped[str] = mapped_column(String(64), primary_key=True)
    version_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)


class ChannelSource(Base):
    __tablename__ = "channel_sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    kol_name: Mapped[str] = mapped_column(String(100))
    group_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("channel_groups.id", ondelete="SET NULL")
    )
    position: Mapped[int] = mapped_column(Integer)
    channel_id: Mapped[str] = mapped_column(String(20), unique=True)
    author_ids: Mapped[list[str]] = mapped_column(JSONB)
    enabled: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(20))
    last_error: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ChannelGroup(Base):
    __tablename__ = "channel_groups"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    position: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CollectorRuntime(Base):
    __tablename__ = "collector_runtime"
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    state: Mapped[str] = mapped_column(String(30))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active_sources: Mapped[int] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(Text)


class CollectorEvent(Base):
    __tablename__ = "collector_events"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    level: Mapped[str] = mapped_column(String(10))
    message: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class MediaObject(Base):
    """按频道和月份独立存放的 R2 对象；同一目录按原始字节 SHA256 去重。"""

    __tablename__ = "media_objects"
    digest: Mapped[str] = mapped_column(String(64))
    object_key: Mapped[str] = mapped_column(String(150), primary_key=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    content_type: Mapped[str] = mapped_column(String(50))
    stored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MediaArchive(Base):
    """随消息事务创建的持久任务；租约过期后可恢复，不修改消息快照。"""

    __tablename__ = "media_archives"
    __table_args__ = (
        Index("ix_media_archives_due", "status", "next_attempt_at"),
        Index("ix_media_archives_message", "message_id", "media_key", unique=True),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    message_id: Mapped[str] = mapped_column(String(20), ForeignKey("messages.message_id"))
    media_key: Mapped[str] = mapped_column(String(64))
    source_url: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))
    attempts: Mapped[int] = mapped_column(Integer)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    object_key: Mapped[str | None] = mapped_column(
        String(150), ForeignKey("media_objects.object_key", name="fk_media_archives_object_key")
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
