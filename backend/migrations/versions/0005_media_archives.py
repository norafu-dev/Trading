"""新增图片归档任务和内容去重对象表，不修改既有消息或删除历史。"""

import sqlalchemy as sa
from alembic import op

revision = "0005_media_archives"
down_revision = "0004_channel_groups"
branch_labels = None
depends_on = None


def upgrade():
    """创建对象与任务，保留失败原因、重试次数和可恢复租约。"""
    op.create_table(
        "media_objects",
        sa.Column("digest", sa.String(64), primary_key=True),
        sa.Column("object_key", sa.String(150), nullable=False, unique=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_type", sa.String(50), nullable=False),
        sa.Column("stored_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "media_archives",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "message_id", sa.String(20), sa.ForeignKey("messages.message_id"), nullable=False
        ),
        sa.Column("media_key", sa.String(64), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("digest", sa.String(64), sa.ForeignKey("media_objects.digest")),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_media_archives_due", "media_archives", ["status", "next_attempt_at"])
    op.create_index(
        "ix_media_archives_message", "media_archives", ["message_id", "media_key"], unique=True
    )


def downgrade():
    """仅移除归档数据库结构；R2 文件不自动删除。"""
    op.drop_table("media_archives")
    op.drop_table("media_objects")
