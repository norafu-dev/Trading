"""配置 Alembic 在线和离线迁移，将 ORM 元数据与数据库版本管理连接起来。"""

import asyncio

from alembic import context

from trading.config import Settings
from trading.db.models import Base
from trading.db.session import create_engine

target_metadata = Base.metadata


def run_migrations(connection):
    """在 Alembic 事务内应用迁移，并提供 ORM 元数据供差异检查。"""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def online():
    """用异步连接运行同步迁移入口，完成或失败后都释放连接池。"""
    engine = create_engine(Settings())
    try:
        async with engine.connect() as connection:
            await connection.run_sync(run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    context.configure(
        url=Settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(online())
