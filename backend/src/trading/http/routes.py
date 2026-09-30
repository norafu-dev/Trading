"""定义面板 HTTP 接口，通过依赖获取数据库并调用业务服务。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from trading.config import Snowflake
from trading.db.media import retry_failed_images, storage_summary
from trading.db.message_browser import channel_messages, message_navigation
from trading.db.models import MediaArchive, MediaObject
from trading.db.session import check_database
from trading.schemas import (
    ChannelGroupDetails,
    ChannelGroupInput,
    ChannelLayoutInput,
    DashboardResponse,
    MessageNavigation,
    MessagePage,
    SourceDetails,
    SourceInput,
    StorageSummary,
)
from trading.services.channel_groups import (
    create_channel_group,
    delete_channel_group,
    save_channel_layout,
    update_channel_group,
)
from trading.services.dashboard import dashboard_snapshot
from trading.services.sources import delete_source, save_source

router = APIRouter(prefix="/api")


def database_engine(request: Request) -> AsyncEngine:
    """从当前应用生命周期取得连接池，不在每次请求中创建新连接池。"""
    return request.app.state.engine


Database = Annotated[AsyncEngine, Depends(database_engine)]


@router.get("/health")
async def health(engine: Database) -> dict[str, str]:
    """检查数据库和迁移可读性，供 Docker 判断 API 服务是否可用。"""
    await check_database(engine)
    return {"status": "ok"}


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard(engine: Database, request: Request) -> DashboardResponse:
    """返回经过响应模型约束的概览快照，包含心跳推导后的进程状态。"""
    return await dashboard_snapshot(engine, request.app.state.settings)


@router.post("/sources", status_code=201, response_model=SourceDetails)
async def create_source(body: SourceInput, engine: Database) -> SourceDetails:
    """接收并校验新来源，调用事务服务保存；重复频道由统一处理器返回 409。"""
    return await save_source(engine, body)


@router.put("/sources/{source_id}", response_model=SourceDetails)
async def edit_source(source_id: UUID, body: SourceInput, engine: Database) -> SourceDetails:
    """按 UUID 更新来源配置，保存成功后等待 Collector 下一轮同步。"""
    return await save_source(engine, body, str(source_id))


@router.delete("/sources/{source_id}", status_code=204)
async def remove_source(source_id: UUID, engine: Database) -> Response:
    """调用事务服务移除来源；成功返回 204，历史消息保留。"""
    await delete_source(engine, str(source_id))
    return Response(status_code=204)


@router.post("/channel-groups", status_code=201, response_model=ChannelGroupDetails)
async def create_group(body: ChannelGroupInput, engine: Database) -> ChannelGroupDetails:
    """创建一个位于列表末尾的频道分组。"""
    return await create_channel_group(engine, body)


@router.put("/channel-groups/{group_id}", response_model=ChannelGroupDetails)
async def rename_group(
    group_id: UUID, body: ChannelGroupInput, engine: Database
) -> ChannelGroupDetails:
    """重命名频道分组。"""
    return await update_channel_group(engine, str(group_id), body)


@router.delete("/channel-groups/{group_id}", status_code=204)
async def remove_group(group_id: UUID, engine: Database) -> Response:
    """删除分组并把其中频道移回未分组。"""
    await delete_channel_group(engine, str(group_id))
    return Response(status_code=204)


@router.put("/channel-layout", status_code=204)
async def reorder_channels(body: ChannelLayoutInput, engine: Database) -> Response:
    """原子保存拖拽后的全部分组和频道位置。"""
    await save_channel_layout(engine, body)
    return Response(status_code=204)


@router.get("/messages/navigation", response_model=MessageNavigation)
async def browse_navigation(engine: Database) -> MessageNavigation:
    """提供自定义分组下的单行频道导航，包括已删除配置留下的历史入口。"""
    return await message_navigation(engine)


@router.get("/messages", response_model=MessagePage)
async def browse_messages(
    engine: Database,
    request: Request,
    channel_id: Snowflake,
    before: Snowflake | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> MessagePage:
    """读取选定频道的一页已采集消息，限制页大小并校验字符串 ID。"""
    return await channel_messages(
        engine, channel_id, before, limit, request.app.state.settings.message_freshness_seconds
    )


@router.get("/media/storage", response_model=StorageSummary)
async def media_storage(engine: Database, request: Request) -> dict:
    """返回非敏感的归档状态和本项目容量，配置齐全不等于连接验收通过。"""
    settings = request.app.state.settings
    return await storage_summary(engine, settings.r2_configured, settings.media_warning_bytes)


@router.post("/media/retry")
async def retry_media(engine: Database, request: Request) -> dict[str, int]:
    """把失败任务恢复为待处理，仅已配置 R2 时允许主动重试。"""
    if request.app.state.storage is None:
        raise HTTPException(status_code=409, detail="请先在本地配置 R2 并重建 API 与 Collector")
    return {"retried": await retry_failed_images(engine)}


@router.get("/media/{archive_id}")
async def archived_image(archive_id: UUID, engine: Database, request: Request) -> RedirectResponse:
    """稳定媒体入口每次生成新签名，不由 API 代理文件流量或返回凭证。"""
    async with engine.connect() as connection:
        key = await connection.scalar(
            select(MediaObject.object_key)
            .join(
                MediaArchive,
                MediaArchive.object_key == MediaObject.object_key,
            )
            .where(MediaArchive.id == str(archive_id), MediaArchive.status == "stored")
        )
    if key is None:
        raise HTTPException(status_code=404, detail="图片尚未归档或记录不存在")
    if request.app.state.storage is None:
        raise HTTPException(status_code=503, detail="R2 读取配置尚未加载")
    return RedirectResponse(request.app.state.storage.read_url(key), status_code=307)
