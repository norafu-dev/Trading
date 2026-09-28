"""创建 FastAPI 应用，管理数据库生命周期、请求来源限制和统一错误响应。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from trading.config import Settings
from trading.db.session import check_database, create_engine
from trading.http.routes import router
from trading.services.channel_groups import ChannelGroupNotFound, ChannelLayoutConflict
from trading.services.sources import DuplicateSource, SourceNotFound


def create_app(settings: Settings | None = None) -> FastAPI:
    """创建独立 API 应用；数据库连接池仅在应用运行期间存在。"""
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """启动时检查数据库，在启动失败或应用退出时始终关闭连接池。"""
        app.state.engine = create_engine(settings)
        try:
            await check_database(app.state.engine)
            yield
        finally:
            await app.state.engine.dispose()

    app = FastAPI(title="Trading Collector", lifespan=lifespan, docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def local_panel_guard(request: Request, call_next):
        # The UI is bound to loopback. Mutations also require our same-origin
        # fetch header, preventing other websites from submitting local forms.
        """限制面板写请求的来源和自定义请求头，并禁止缓存状态响应。"""
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            if request.headers.get("x-requested-with") != "trading-panel" or (
                origin
                and origin
                not in {"http://localhost:3000", "http://127.0.0.1:3000", "http://web:3000"}
            ):
                return JSONResponse({"detail": "请求来源不受支持"}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, error: SQLAlchemyError):
        """把数据库异常转换为脱敏的 503，避免 SQL 或参数出现在响应中。"""
        return JSONResponse({"detail": "数据库暂时不可用，请稍后重试"}, status_code=503)

    @app.exception_handler(SourceNotFound)
    async def source_not_found(request: Request, error: SourceNotFound):
        """把不存在的来源转换为 404，供表单和来源列表显示业务反馈。"""
        return JSONResponse({"detail": "采集来源不存在"}, status_code=404)

    @app.exception_handler(DuplicateSource)
    async def duplicate_source(request: Request, error: DuplicateSource):
        """把重复频道配置转换为 409，提示编辑已经存在的来源。"""
        return JSONResponse({"detail": "该频道或 Thread 已存在，请编辑现有来源"}, status_code=409)

    @app.exception_handler(ChannelGroupNotFound)
    async def channel_group_not_found(request: Request, error: ChannelGroupNotFound):
        """把不存在的频道分组转换为 404。"""
        return JSONResponse({"detail": "频道分组不存在"}, status_code=404)

    @app.exception_handler(ChannelLayoutConflict)
    async def channel_layout_conflict(request: Request, error: ChannelLayoutConflict):
        """提示页面刷新过期导航，避免拖拽覆盖更新后的分组配置。"""
        return JSONResponse({"detail": "频道列表已变化，请刷新后重新拖拽"}, status_code=409)

    app.include_router(router)
    return app
