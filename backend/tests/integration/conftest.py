"""集成测试数据库夹具；只允许清理独立 test-postgres 上的 trading_test。"""

import os

import pytest
import pytest_asyncio
from sqlalchemy import delete, update

from trading.config import Settings
from trading.db.models import (
    ChannelGroup,
    ChannelSource,
    CollectorEvent,
    CollectorRuntime,
    MediaArchive,
    MediaObject,
    Message,
    MessageVersion,
)
from trading.db.session import create_engine


@pytest_asyncio.fixture
async def engine():
    """连接独立测试库并清理测试记录；校验库名和主机，防止误清采集数据。"""
    if os.environ.get("RUN_DB_TESTS") != "1":
        pytest.skip("Run through the Docker Compose tests service")
    settings = Settings()
    if settings.db_name != "trading_test" or settings.db_host != "test-postgres":
        pytest.fail("Refusing cleanup outside the isolated Compose test database")
    engine = create_engine(settings)
    try:
        async with engine.begin() as connection:
            for model in (
                MediaArchive,
                MediaObject,
                MessageVersion,
                Message,
                ChannelSource,
                ChannelGroup,
                CollectorEvent,
            ):
                await connection.execute(delete(model))
            await connection.execute(
                update(CollectorRuntime).values(
                    state="stopped",
                    heartbeat_at=None,
                    active_sources=0,
                    last_error=None,
                    last_saved_at=None,
                    last_message_at=None,
                    source_sync_at=None,
                    connected_at=None,
                    started_at=None,
                )
            )
        yield engine
    finally:
        await engine.dispose()
