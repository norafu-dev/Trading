"""移除头像配置，并增加可拖拽的频道分组与排序字段。"""

import sqlalchemy as sa
from alembic import op

revision = "0004_channel_groups"
down_revision = "0003_source_kol_profile"
branch_labels = None
depends_on = None


def upgrade():
    """创建分组表，为来源增加分组和位置，并移除不再使用的头像字段。"""
    op.create_table(
        "channel_groups",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column(
        "channel_sources", sa.Column("position", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("channel_sources", sa.Column("group_id", sa.String(36), nullable=True))
    op.create_foreign_key(
        "fk_channel_sources_group_id",
        "channel_sources",
        "channel_groups",
        ["group_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_column("channel_sources", "kol_avatar_url")
    op.alter_column("channel_sources", "position", server_default=None)


def downgrade():
    """恢复头像字段，并移除频道分组和排序结构。"""
    op.add_column("channel_sources", sa.Column("kol_avatar_url", sa.String(200), nullable=True))
    op.drop_constraint("fk_channel_sources_group_id", "channel_sources", type_="foreignkey")
    op.drop_column("channel_sources", "group_id")
    op.drop_column("channel_sources", "position")
    op.drop_table("channel_groups")
