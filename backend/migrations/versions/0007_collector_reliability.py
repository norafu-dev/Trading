"""添加删除墓碑、采集来源和独立补采游标；不推测既有消息的投递来源。"""

import sqlalchemy as sa
from alembic import op

revision = "0007_collector_reliability"
down_revision = "0006_channel_media_layout"
branch_labels = None
depends_on = None


def upgrade():
    """保留全部旧消息与图片，并为历史扫描建立可恢复的数据结构。"""
    op.add_column(
        "messages",
        sa.Column("first_delivery", sa.String(20), nullable=False, server_default="unknown"),
    )
    op.add_column("messages", sa.Column("deleted_at", sa.DateTime(timezone=True)))
    op.add_column(
        "message_versions",
        sa.Column("observation_source", sa.String(20), nullable=False, server_default="unknown"),
    )
    op.alter_column("messages", "first_delivery", server_default=None)
    op.alter_column("message_versions", "observation_source", server_default=None)
    op.create_table(
        "message_deletions",
        sa.Column("message_id", sa.String(20), primary_key=True),
        sa.Column("channel_id", sa.String(20), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "channel_checkpoints",
        sa.Column("channel_id", sa.String(20), primary_key=True),
        sa.Column("cursor_id", sa.String(20), nullable=False),
        sa.Column("target_id", sa.String(20)),
        sa.Column("coverage_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.Text()),
        sa.Column("last_completed_at", sa.DateTime(timezone=True)),
    )


def downgrade():
    """移除本次结构；退回时不删除原始消息或图片。"""
    op.drop_table("channel_checkpoints")
    op.drop_table("message_deletions")
    op.drop_column("message_versions", "observation_source")
    op.drop_column("messages", "deleted_at")
    op.drop_column("messages", "first_delivery")
