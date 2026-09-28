"""创建隐藏 SQL 参数的异步连接池，并检查数据库迁移是否可用。"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from trading.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    """创建具备连接探活的异步连接池，并隐藏异常中的 SQL 参数。"""
    return create_async_engine(settings.database_url, pool_pre_ping=True, hide_parameters=True)


async def check_database(engine: AsyncEngine) -> str:
    """检查迁移版本及消息表可访问性；未迁移时抛出明确的启动错误。"""
    async with engine.connect() as connection:
        revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
        await connection.execute(text("SELECT message_id FROM messages LIMIT 0"))
    if not revision:
        raise RuntimeError("Database migration missing")
    return str(revision)
