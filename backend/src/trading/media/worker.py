"""独立异步图片归档任务；持久队列、有限重试和历史链接刷新不阻塞消息采集。"""

import asyncio
import hashlib
import logging

import aiohttp
import discord
from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from trading.collector.messages import normalize_message
from trading.config import Settings
from trading.db.control import add_event
from trading.db.media import (
    claim_image,
    fail_image,
    finish_image,
    seed_historical_images,
    storage_summary,
)
from trading.db.models import MediaObject
from trading.media.candidates import discord_media_url, image_candidates, image_content_type
from trading.media.layout import image_object_key
from trading.media.storage import R2Storage

logger = logging.getLogger(__name__)


class ImageArchiveError(Exception):
    """可向面板展示的脱敏归档错误，区分暂时失败和永久失败。"""

    def __init__(self, message: str, terminal: bool = False, refresh: bool = False) -> None:
        """保存公开错误分类，不包含下载链接、签名或 Discord/R2 凭证。"""
        super().__init__(message)
        self.terminal = terminal
        self.refresh = refresh


async def download_image(
    session: aiohttp.ClientSession, url: str, max_bytes: int
) -> tuple[bytes, str]:
    """流式下载到有限内存，禁用重定向并验证位图签名，绝不发送 Discord Token。"""
    if not discord_media_url(url):
        raise ImageArchiveError("图片地址不在允许的 Discord 域名内", terminal=True)
    async with session.get(url, allow_redirects=False) as response:
        if response.status in {403, 404}:
            raise ImageArchiveError("Discord 图片链接已过期或文件不存在", refresh=True)
        if response.status != 200:
            raise ImageArchiveError("Discord CDN 暂时无法下载图片")
        if response.content_length is not None and response.content_length > max_bytes:
            raise ImageArchiveError("图片超过单文件归档上限", terminal=True)
        data = bytearray()
        async for chunk in response.content.iter_chunked(64 * 1024):
            data.extend(chunk)
            if len(data) > max_bytes:
                raise ImageArchiveError("图片超过单文件归档上限", terminal=True)
        content_type = image_content_type(data)
        if content_type is None:
            raise ImageArchiveError("下载内容不是支持的 PNG/JPEG/GIF/WebP/AVIF 图片", terminal=True)
        return bytes(data), content_type


class MediaArchiver:
    """单消费者顺序归档，使用 Discord 已登录客户端仅刷新指定消息的媒体链接。"""

    def __init__(self, engine: AsyncEngine, client: discord.Client, settings: Settings) -> None:
        """保存运行依赖；R2 配置缺失时不创建 SDK 客户端。"""
        self.engine = engine
        self.client = client
        self.settings = settings
        self.capacity_warned = False

    async def refreshed_url(self, job: dict) -> str:
        """重新读取原消息并匹配同一图片；编辑后换图不能冒充历史原图。"""
        async with asyncio.timeout(30):
            channel = self.client.get_channel(
                int(job["channel_id"])
            ) or await self.client.fetch_channel(int(job["channel_id"]))
            if not isinstance(channel, (discord.TextChannel, discord.Thread)):
                raise ImageArchiveError("原消息频道已不可访问", terminal=True)
            message = await channel.fetch_message(int(job["message_id"]))
        for candidate in image_candidates(normalize_message(message).model_dump(mode="json")):
            if candidate.key == job["media_key"]:
                return candidate.url
        raise ImageArchiveError("原图片已删除或消息已更换图片，无法恢复该历史原图", terminal=True)

    async def archive(self, job: dict, session: aiohttp.ClientSession, storage: R2Storage) -> None:
        """下载、必要时刷新链接、按原始字节去重并上传，最后提交任务状态。"""
        try:
            data, content_type = await download_image(
                session, job["source_url"], self.settings.media_max_image_bytes
            )
        except ImageArchiveError as error:
            if not error.refresh:
                raise
            url = await self.refreshed_url(job)
            data, content_type = await download_image(
                session, url, self.settings.media_max_image_bytes
            )
        digest = hashlib.sha256(data).hexdigest()
        object_key = image_object_key(
            job["channel_id"], job["message_created_at"], digest, content_type
        )
        async with self.engine.connect() as connection:
            existing = await connection.scalar(
                select(MediaObject.object_key).where(MediaObject.object_key == object_key)
            )
        if existing is None:
            await storage.upload(object_key, data, content_type)
        await finish_image(self.engine, job, digest, len(data), content_type)
        summary = await storage_summary(self.engine, True, self.settings.media_warning_bytes)
        if summary["capacity_warning"] and not self.capacity_warned:
            await add_event(
                self.engine, "R2 图片容量达到预警阈值，原图继续保留，请查看图片归档面板", "warning"
            )
            self.capacity_warned = True

    async def process(self, job: dict, session: aiohttp.ClientSession, storage: R2Storage) -> None:
        """把下载、权限、对象存储故障转成持久状态，单图片失败不会结束采集。"""
        try:
            await self.archive(job, session, storage)
        except ImageArchiveError as error:
            await fail_image(self.engine, job, str(error), error.terminal)
        except (discord.Forbidden, discord.NotFound):
            await fail_image(
                self.engine, job, "原消息已删除或账号无权访问，无法刷新图片", terminal=True
            )
        except (aiohttp.ClientError, discord.HTTPException, OSError, TimeoutError):
            await fail_image(self.engine, job, "图片下载或消息刷新暂时失败，将有限重试")
        except (BotoCoreError, ClientError):
            await fail_image(self.engine, job, "R2 上传失败，请检查本地配置、桶权限与网络")
        except Exception as error:
            # 程序或第三方库的意外错误也持久化并有限重试，不能一直留在处理中。
            logger.error("media_job_retry error_type=%s", type(error).__name__)
            await fail_image(
                self.engine, job, f"图片归档处理异常（{type(error).__name__}），将有限重试"
            )

    async def run(self) -> None:
        """持续运行归档；数据库暂不可用时退避，未配置时只补建持久任务。"""
        storage = R2Storage(self.settings) if self.settings.r2_configured else None
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=45), trust_env=False
            ) as session:
                seeded = False
                while not self.client.is_closed():
                    try:
                        if not seeded:
                            await seed_historical_images(self.engine)
                            seeded = True
                        if storage is None:
                            await add_event(
                                self.engine,
                                "R2 尚未配置：图片归档任务已留存，配置后重启服务即可补存",
                                "warning",
                            )
                            return
                        if not self.client.is_ready():
                            await asyncio.sleep(5)
                            continue
                        job = await claim_image(self.engine)
                        if job:
                            await self.process(job, session, storage)
                        else:
                            await asyncio.sleep(5)
                    except asyncio.CancelledError:
                        raise
                    except Exception as error:
                        # 日志只记录类型，避免 SDK 或 HTTP 原始异常泄露签名链接。
                        logger.error("media_worker_retry error_type=%s", type(error).__name__)
                        await asyncio.sleep(10)
        finally:
            if storage is not None:
                storage.close()
