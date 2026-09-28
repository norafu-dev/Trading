"""编排频道分组与拖拽布局事务，并防止过期页面覆盖较新的配置。"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncEngine

from trading.db.channel_groups import (
    current_layout_ids,
    insert_group,
    next_group_position,
    remove_group,
    rename_group,
    write_layout,
)
from trading.schemas import ChannelGroupDetails, ChannelGroupInput, ChannelLayoutInput


class ChannelGroupNotFound(Exception):
    """请求的频道分组不存在。"""


class ChannelLayoutConflict(Exception):
    """页面布局已过期，需要刷新后再次拖拽。"""


async def create_channel_group(engine: AsyncEngine, body: ChannelGroupInput) -> ChannelGroupDetails:
    """在末尾创建频道分组。"""
    async with engine.begin() as connection:
        return await insert_group(
            connection,
            body,
            str(uuid4()),
            await next_group_position(connection),
            datetime.now(UTC),
        )


async def update_channel_group(
    engine: AsyncEngine, group_id: str, body: ChannelGroupInput
) -> ChannelGroupDetails:
    """重命名频道分组，不改变其中频道。"""
    async with engine.begin() as connection:
        group = await rename_group(connection, group_id, body, datetime.now(UTC))
        if group is None:
            raise ChannelGroupNotFound
        return group


async def delete_channel_group(engine: AsyncEngine, group_id: str) -> None:
    """删除分组并把所属频道移回未分组。"""
    async with engine.begin() as connection:
        if not await remove_group(connection, group_id):
            raise ChannelGroupNotFound


async def save_channel_layout(engine: AsyncEngine, body: ChannelLayoutInput) -> None:
    """校验完整 ID 集合后原子保存分组和频道顺序。"""
    async with engine.begin() as connection:
        existing_groups, existing_sources = await current_layout_ids(connection)
        submitted_groups = {str(item.group_id) for item in body.groups}
        submitted_sources = {str(item.source_id) for item in body.channels}
        if (
            len(submitted_groups) != len(body.groups)
            or len(submitted_sources) != len(body.channels)
            or submitted_groups != existing_groups
            or submitted_sources != existing_sources
        ):
            raise ChannelLayoutConflict
        if any(
            item.group_id is not None and str(item.group_id) not in existing_groups
            for item in body.channels
        ):
            raise ChannelLayoutConflict
        await write_layout(connection, body)
