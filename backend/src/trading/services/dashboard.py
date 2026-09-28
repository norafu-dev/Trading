"""组合概览查询结果，并根据心跳有效期解释 Collector 是否在线。"""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncEngine

from trading.db.dashboard import read_dashboard
from trading.schemas import DashboardResponse, RuntimeDetails, RuntimeStatus

HEARTBEAT_TIMEOUT_SECONDS = 30


def visible_runtime(runtime: RuntimeDetails, now: datetime) -> RuntimeStatus:
    """根据心跳年龄推导进程存活状态；已停止或错误状态不会被新心跳误判为在线。"""
    age = None
    if runtime.heartbeat_at is not None:
        age = (now - runtime.heartbeat_at).total_seconds()
    terminal = runtime.state in {"stopped", "error"}
    alive = age is not None and 0 <= age < HEARTBEAT_TIMEOUT_SECONDS and not terminal
    state = runtime.state
    if not terminal and not alive:
        state = "stale"
    return RuntimeStatus(
        **{**runtime.model_dump(), "state": state}, process_alive=alive, heartbeat_age_seconds=age
    )


async def dashboard_snapshot(engine: AsyncEngine) -> DashboardResponse:
    """组合数据库记录与推导状态，生成供前端使用的完整响应。"""
    records = await read_dashboard(engine)
    now = datetime.now(UTC)
    return DashboardResponse(
        sources=records.sources,
        runtime=visible_runtime(records.runtime, now),
        total_messages=records.total_messages,
        messages=records.messages,
        events=records.events,
        server_time=now,
    )
