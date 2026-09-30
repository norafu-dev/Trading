"""解析采集、检查和显式媒体迁移命令并管理数据库资源与脱敏的进程退出状态。"""

import argparse
import asyncio
import contextlib
import json
import logging
import sys

from sqlalchemy.exc import SQLAlchemyError

from trading.collector.runtime import run_collector
from trading.config import Settings
from trading.db.control import add_event, update_runtime
from trading.db.session import check_database, create_engine
from trading.media.relocate import reorganize_media
from trading.media.storage import R2Storage


async def run(command: str) -> None:
    """检查数据库并按命令启动采集；失败时写入脱敏状态，最后释放连接池。"""
    settings = Settings()
    logging.basicConfig(
        level=settings.log_level,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("discord").setLevel(logging.CRITICAL)
    logging.getLogger("sqlalchemy").setLevel(logging.ERROR)
    engine = create_engine(settings)
    failed = False
    try:
        revision = await check_database(engine)
        logging.info("database_ready revision=%s", revision)
        if command == "check":
            return
        if command == "reorganize-media":
            if not settings.r2_configured:
                raise RuntimeError("R2 configuration is missing")
            storage = R2Storage(settings)
            try:
                result = await reorganize_media(engine, storage)
                print(json.dumps(result))
            finally:
                storage.close()
            return
        await run_collector(engine, settings.discord_token.get_secret_value().strip(), settings)
    except Exception as error:
        failed = True
        if command == "collect":
            with contextlib.suppress(SQLAlchemyError, OSError, TimeoutError):
                reason = f"启动或运行失败（{type(error).__name__}），请检查 Token、网络与数据库"
                await update_runtime(engine, state="error", last_error=reason, active_sources=0)
                await add_event(engine, reason, "error")
        raise
    finally:
        if command == "collect" and not failed:
            with contextlib.suppress(SQLAlchemyError, OSError, TimeoutError):
                await update_runtime(engine, state="stopped", active_sources=0)
        await engine.dispose()


def main() -> None:
    """解析命令行参数并运行异步入口；失败时返回非零退出码，不打印原始异常。"""
    parser = argparse.ArgumentParser(description="M1 Discord ingestion")
    parser.add_argument("command", choices=["check", "collect", "reorganize-media"])
    args = parser.parse_args()
    try:
        asyncio.run(run(args.command))
    except KeyboardInterrupt:
        pass
    except Exception as error:
        print(
            f"Trading command failure ({type(error).__name__}); inspect panel and configuration.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
