"""启动 Collector；缺少 Token 时维持心跳，收到退出信号时释放连接。"""

import asyncio
import signal
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncEngine

from trading.collector.client import HEARTBEAT_INTERVAL_SECONDS, Collector
from trading.db.control import add_event, update_runtime


async def wait_for_configuration(engine: AsyncEngine) -> None:
    """Token 缺失时仅报告心跳，直到收到退出信号；退出时移除信号处理器。"""
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stopped.set)
    try:
        while not stopped.is_set():
            await update_runtime(engine, heartbeat_at=datetime.now(UTC), state="missing_token")
            try:
                await asyncio.wait_for(stopped.wait(), timeout=HEARTBEAT_INTERVAL_SECONDS)
            except TimeoutError:
                continue
    finally:
        for signum in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(signum)


async def run_collector(engine: AsyncEngine, token: str) -> None:
    """初始化进程状态，再等待配置或连接 Discord；负责信号绑定和资源释放。"""
    now = datetime.now(UTC)
    await update_runtime(
        engine,
        started_at=now,
        heartbeat_at=now,
        active_sources=0,
        connected_at=None,
        source_sync_at=None,
        last_error=None,
        state="connecting" if token else "missing_token",
    )
    await add_event(
        engine,
        "Collector 服务已启动"
        if token
        else "Collector 等待本地 DISCORD_TOKEN 配置，尚未连接 Discord",
    )
    if not token:
        await wait_for_configuration(engine)
        return
    client = Collector(engine)
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, lambda: asyncio.create_task(client.close()))
    try:
        async with client:
            client.monitor_task = asyncio.create_task(client.monitor())
            # discord.py-self 使用用户账号 Token；不传普通 Bot 客户端的认证参数。
            await client.start(token, reconnect=True)
        if client.failed:
            raise RuntimeError("Collector event failure")
    finally:
        for signum in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(signum)
