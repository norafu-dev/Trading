"""为采集来源增加人工维护的 KOL 名称和头像。"""

import sqlalchemy as sa
from alembic import op

revision = "0003_source_kol_profile"
down_revision = "0002_control_panel"
branch_labels = None
depends_on = None


def upgrade():
    """增加展示资料，并以现有来源名称初始化 KOL 名称。"""
    op.add_column("channel_sources", sa.Column("kol_name", sa.String(100), nullable=True))
    op.add_column("channel_sources", sa.Column("kol_avatar_url", sa.String(200), nullable=True))
    op.execute("UPDATE channel_sources SET kol_name = name")
    op.alter_column("channel_sources", "kol_name", nullable=False)


def downgrade():
    """移除来源的 KOL 展示资料。"""
    op.drop_column("channel_sources", "kol_avatar_url")
    op.drop_column("channel_sources", "kol_name")
