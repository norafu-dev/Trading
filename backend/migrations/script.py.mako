"""${message}：迁移生成模板，请在生成后补充该版本具体的数据结构变更说明。"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}

def upgrade():
    """应用当前版本的数据结构变更；生成后核对操作与已有数据兼容性。"""
    ${upgrades if upgrades else "pass"}

def downgrade():
    """撤销当前版本的变更；执行前确认需要保留的数据。"""
    ${downgrades if downgrades else "pass"}
