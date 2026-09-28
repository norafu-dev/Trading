"""管理面板迁移：创建来源、Collector 状态和事件表，并初始化主进程记录。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_control_panel"
down_revision = "0001_messages"
branch_labels = None
depends_on = None


def upgrade():
    """创建来源、运行状态和事件表。"""
    op.create_table(
        "channel_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("channel_id", sa.String(20), nullable=False, unique=True),
        sa.Column("author_ids", postgresql.JSONB(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    runtime = op.create_table(
        "collector_runtime",
        sa.Column("id", sa.String(20), primary_key=True),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_saved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active_sources", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
    )
    op.bulk_insert(runtime, [{"id": "primary", "state": "stopped", "active_sources": 0}])
    op.create_table(
        "collector_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("level", sa.String(10), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_collector_events_occurred_at", "collector_events", ["occurred_at"])


def downgrade():
    """撤销来源、运行状态和事件表。"""
    op.drop_table("collector_events")
    op.drop_table("collector_runtime")
    op.drop_table("channel_sources")
