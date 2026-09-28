"""初始消息迁移：创建当前消息表和去重版本表；仅调整说明，不改变迁移操作。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_messages"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """创建消息与版本表。"""
    op.create_table(
        "messages",
        sa.Column("message_id", sa.String(20), primary_key=True),
        sa.Column("channel_id", sa.String(20), nullable=False),
        sa.Column("author_id", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_messages_channel_created", "messages", ["channel_id", "created_at"])
    op.create_index("ix_messages_author_created", "messages", ["author_id", "created_at"])
    op.create_table(
        "message_versions",
        sa.Column(
            "message_id", sa.String(20), sa.ForeignKey("messages.message_id"), primary_key=True
        ),
        sa.Column("fingerprint", sa.String(64), primary_key=True),
        sa.Column("version_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
    )


def downgrade():
    """撤销消息与版本表。"""
    op.drop_table("message_versions")
    op.drop_table("messages")
