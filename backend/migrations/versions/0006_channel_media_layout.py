"""对象改用路径主键，允许不同频道与月份独立保存相同内容，保留旧对象引用。"""

import sqlalchemy as sa
from alembic import op

revision = "0006_channel_media_layout"
down_revision = "0005_media_archives"
branch_labels = None
depends_on = None


def upgrade():
    """转换引用契约；仅改数据库结构，云端迁移由显式维护命令执行。"""
    op.add_column("media_archives", sa.Column("object_key", sa.String(150), nullable=True))
    op.execute("""
        UPDATE media_archives AS archive
        SET object_key = object.object_key
        FROM media_objects AS object
        WHERE archive.digest = object.digest
    """)
    op.drop_constraint("media_archives_digest_fkey", "media_archives", type_="foreignkey")
    op.drop_column("media_archives", "digest")
    op.drop_constraint("media_objects_pkey", "media_objects", type_="primary")
    op.drop_constraint("media_objects_object_key_key", "media_objects", type_="unique")
    op.create_primary_key("media_objects_pkey", "media_objects", ["object_key"])
    op.create_foreign_key(
        "fk_media_archives_object_key",
        "media_archives",
        "media_objects",
        ["object_key"],
        ["object_key"],
    )


def downgrade():
    """多目录可拥有同哈希，不能无损退回全局哈希主键，禁止破坏性自动降级。"""
    raise RuntimeError(
        "Channel media layout cannot be downgraded without an explicit data migration"
    )
