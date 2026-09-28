"""执行频道分组 CRUD 和拖拽排序 SQL；事务由 Service 统一管理。"""

from datetime import datetime

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from trading.db.models import ChannelGroup, ChannelSource
from trading.schemas import ChannelGroupDetails, ChannelGroupInput, ChannelLayoutInput


async def insert_group(
    connection: AsyncConnection,
    body: ChannelGroupInput,
    group_id: str,
    position: int,
    now: datetime,
) -> ChannelGroupDetails:
    """在指定末尾位置新增分组并返回保存结果。"""
    row = (
        (
            await connection.execute(
                insert(ChannelGroup)
                .values(
                    id=group_id,
                    name=body.name,
                    position=position,
                    created_at=now,
                    updated_at=now,
                )
                .returning(ChannelGroup.id, ChannelGroup.name, ChannelGroup.position)
            )
        )
        .mappings()
        .one()
    )
    return ChannelGroupDetails.model_validate(row)


async def rename_group(
    connection: AsyncConnection, group_id: str, body: ChannelGroupInput, now: datetime
) -> ChannelGroupDetails | None:
    """重命名存在的分组；找不到时返回空供 Service 转换为领域错误。"""
    row = (
        (
            await connection.execute(
                update(ChannelGroup)
                .where(ChannelGroup.id == group_id)
                .values(name=body.name, updated_at=now)
                .returning(ChannelGroup.id, ChannelGroup.name, ChannelGroup.position)
            )
        )
        .mappings()
        .first()
    )
    return ChannelGroupDetails.model_validate(row) if row else None


async def remove_group(connection: AsyncConnection, group_id: str) -> bool:
    """删除分组；外键把其中频道自动移回未分组。"""
    deleted = await connection.scalar(
        delete(ChannelGroup).where(ChannelGroup.id == group_id).returning(ChannelGroup.id)
    )
    return deleted is not None


async def next_group_position(connection: AsyncConnection) -> int:
    """读取当前分组数量，作为新分组的末尾位置。"""
    return len((await connection.execute(select(ChannelGroup.id))).all())


async def current_layout_ids(connection: AsyncConnection) -> tuple[set[str], set[str]]:
    """返回当前分组和来源 ID，用于拒绝基于过期导航提交的完整布局。"""
    groups = set((await connection.scalars(select(ChannelGroup.id))).all())
    sources = set((await connection.scalars(select(ChannelSource.id))).all())
    return groups, sources


async def write_layout(connection: AsyncConnection, body: ChannelLayoutInput) -> None:
    """逐项写入完整布局；调用前已验证所有 ID 恰好覆盖当前配置。"""
    for group in body.groups:
        await connection.execute(
            update(ChannelGroup)
            .where(ChannelGroup.id == str(group.group_id))
            .values(position=group.position)
        )
    for channel in body.channels:
        await connection.execute(
            update(ChannelSource)
            .where(ChannelSource.id == str(channel.source_id))
            .values(
                group_id=str(channel.group_id) if channel.group_id else None,
                position=channel.position,
            )
        )
