"""R2 S3 适配；凭证只在服务端使用，私有桶以短期签名 GET 链接读取。"""

import asyncio
import hashlib

import boto3
from botocore.config import Config

from trading.config import Settings
from trading.media.layout import LEGACY_PREFIX, is_legacy_key


class R2Storage:
    """同步 SDK 放到线程执行，避免图片上传阻塞 Discord 事件循环。"""

    def __init__(self, settings: Settings) -> None:
        """显式传入 R2 凭证，不使用 AWS 默认凭证链或访问实例元数据。"""
        self.bucket = settings.r2_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=settings.r2_access_key_id.get_secret_value(),
            aws_secret_access_key=settings.r2_secret_access_key.get_secret_value(),
            region_name="auto",
            config=Config(
                signature_version="s3v4",
                connect_timeout=5,
                read_timeout=20,
                retries={"mode": "standard", "total_max_attempts": 2},
            ),
        )

    async def upload(self, object_key: str, data: bytes, content_type: str) -> None:
        """原字节写入频道与月份路径；重试覆盖同一对象键，不产生额外文件。"""
        await asyncio.to_thread(
            self.client.put_object,
            Bucket=self.bucket,
            Key=object_key,
            Body=data,
            ContentType=content_type,
            CacheControl="private, max-age=3600",
        )

    def verify_object(self, object_key: str, digest: str, size: int) -> None:
        """流式读取目标原图并校验完整 SHA256 和大小，失败时禁止切换引用或删除。"""
        response = self.client.get_object(Bucket=self.bucket, Key=object_key)
        body = response["Body"]
        hasher = hashlib.sha256()
        count = 0
        try:
            for chunk in body.iter_chunks(chunk_size=64 * 1024):
                count += len(chunk)
                if count > size:
                    raise ValueError("Migrated image exceeds expected size")
                hasher.update(chunk)
        finally:
            body.close()
        if count != size or hasher.hexdigest() != digest:
            raise ValueError("Migrated image verification failed")

    async def copy_verified(self, source_key: str, target_key: str, digest: str, size: int) -> None:
        """桶内复制旧原图并验证新对象，保留原图字节与 Content-Type。"""
        if not is_legacy_key(source_key) or target_key.startswith(LEGACY_PREFIX):
            raise ValueError("Unsupported media relocation")
        await asyncio.to_thread(
            self.client.copy_object,
            Bucket=self.bucket,
            Key=target_key,
            CopySource={"Bucket": self.bucket, "Key": source_key},
        )
        await asyncio.to_thread(self.verify_object, target_key, digest, size)

    async def legacy_keys(self) -> list[str]:
        """只列举本项目旧前缀下的对象，不遍历或清理其他目录。"""

        def list_keys() -> list[str]:
            """分页读取 S3 对象清单，不输出桶名、签名或凭证。"""
            pages = self.client.get_paginator("list_objects_v2").paginate(
                Bucket=self.bucket,
                Prefix=LEGACY_PREFIX,
            )
            return [item["Key"] for page in pages for item in page.get("Contents", [])]

        return await asyncio.to_thread(list_keys)

    async def delete_legacy(self, object_key: str) -> None:
        """仅供显式迁移清理旧对象，拒绝删除新目录和桶内无关文件。"""
        if not is_legacy_key(object_key):
            raise ValueError("Refusing deletion outside the generated legacy layout")
        await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket, Key=object_key)

    def read_url(self, object_key: str) -> str:
        """签名只在响应时生成，不把会过期的 R2 链接持久化到数据库。"""
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": object_key},
            ExpiresIn=3600,
        )

    def close(self) -> None:
        """释放 SDK 的 HTTP 连接池。"""
        self.client.close()
