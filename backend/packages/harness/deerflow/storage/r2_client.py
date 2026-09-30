"""DeerFlow 统一存储层 — R2 S3-compatible 异步客户端。

支持：
  - 文件上传（buffer / permanent 双桶）
  - Base64 上传
  - 预签名上传 URL
  - 对象删除
  - 对象列表查询
  - 连接状态检查

用法::

    # 上传文件
    result = await upload_to_r2(
        data=b"..." ,
        mime="image/png",
        category="asset",
        owner_id="user_xxx",
        ext="png",
        storage_class=StorageClass.BUFFER,
    )

    # 获取预签名 URL
    presigned = await get_presigned_upload_url(
        category="asset",
        owner_id="user_xxx",
        mime="image/png",
        ext="png",
    )
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from deerflow.storage.config import R2Config, get_r2_config
from deerflow.storage.models import (
    DeleteResult,
    PresignedUrlResult,
    StorageClass,
    StorageStatus,
    UploadResult,
    generate_r2_key,
)

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

logger = logging.getLogger(__name__)

# ─── boto3 可选导入 ─────────────────────────────────────────────────────

try:
    import boto3
    from botocore.config import Config as BotoConfig

    _boto3_available = True
except ImportError:
    boto3 = None
    BotoConfig = None
    _boto3_available = False


# ─── 客户端 ─────────────────────────────────────────────────────────────


class R2Client:
    """R2 S3-compatible 存储客户端。

    封装 boto3 S3 客户端，提供 R2 上传、删除、预签名 URL 等操作。
    与前端 src/lib/storage/r2-client.ts 的 API 语义对齐。
    """

    def __init__(self, config: R2Config | None = None) -> None:
        self._config = config or get_r2_config()
        self._client: S3Client | None = None

    @property
    def config(self) -> R2Config:
        return self._config

    @property
    def available(self) -> bool:
        """检查 R2 是否可用（有配置 + boto3 已安装）。"""
        if not _boto3_available:
            return False
        if not self._config.is_configured:
            return False
        return True

    def _get_client(self) -> S3Client:
        """获取（或创建）boto3 S3 客户端。"""
        if self._client is not None:
            return self._client
        if not _boto3_available:
            raise RuntimeError("boto3 is not installed. Install with: pip install boto3")
        if not self._config.is_configured:
            raise RuntimeError("R2 is not configured. Set R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ENDPOINT, and R2_BUCKET_BUFFER")

        self._client = boto3.client(
            "s3",
            endpoint_url=self._config.endpoint_url,
            aws_access_key_id=self._config.access_key_id,
            aws_secret_access_key=self._config.secret_access_key,
            config=BotoConfig(
                s3={"addressing_style": "path"},
                connect_timeout=10,
                read_timeout=60,
                retries={"max_attempts": 2},
            ),
        )
        return self._client

    async def upload(
        self,
        data: bytes,
        mime: str,
        category: str,
        owner_id: str,
        ext: str,
        *,
        storage_class: StorageClass = StorageClass.BUFFER,
        suggested_name: str | None = None,
        key_override: str | None = None,
    ) -> UploadResult:
        """上传文件到 R2。

        Args:
            data: 文件二进制数据。
            mime: MIME 类型，如 "image/png"。
            category: 内容类别，与前端 ContentCategory 对齐。
            owner_id: 所有者 ID（用户 ID 或项目 ID）。
            ext: 文件扩展名（不含点），如 "png"。
            storage_class: 存储类别，buffer（临时）或 permanent（永久）。
            suggested_name: 可读文件名（可选），用于生成有意义的 key。
            key_override: 强制指定 object key（可选），覆盖自动生成。

        Returns:
            UploadResult 包含 key、url、size 等。
        """
        client = self._get_client()
        is_permanent = storage_class == StorageClass.PERMANENT
        bucket = self._config.get_bucket(permanent=is_permanent)

        key = key_override or generate_r2_key(
            category=category,
            owner_id=owner_id,
            ext=ext,
            suggested_name=suggested_name,
        )

        cache_control = "public, max-age=31536000, immutable" if is_permanent else "public, max-age=86400"

        try:
            client.put_object(
                Bucket=bucket,
                Key=key,
                Body=data,
                ContentType=mime,
                CacheControl=cache_control,
            )
        except Exception as e:
            logger.error("R2 upload failed (bucket=%s, key=%s): %s", bucket, key, e)
            return UploadResult(
                key=key,
                url="",
                size=len(data),
                bucket_name=bucket,
                storage_class=storage_class,
                success=False,
                error=str(e),
            )

        url = self._config.build_cdn_url(key, permanent=is_permanent)
        logger.info("R2 upload success (bucket=%s, key=%s, size=%d)", bucket, key, len(data))

        return UploadResult(
            key=key,
            url=url,
            size=len(data),
            bucket_name=bucket,
            storage_class=storage_class,
            success=True,
        )

    async def upload_base64(
        self,
        base64_data: str,
        category: str,
        owner_id: str,
        ext: str,
        *,
        storage_class: StorageClass = StorageClass.BUFFER,
        suggested_name: str | None = None,
    ) -> UploadResult:
        """上传 Base64 编码的数据到 R2。

        Args:
            base64_data: Base64 编码的字符串（可含 "data:image/png;base64," 前缀）。
            category: 内容类别。
            owner_id: 所有者 ID。
            ext: 文件扩展名。
            storage_class: 存储类别。
            suggested_name: 可读文件名。

        Returns:
            UploadResult。
        """
        # 提取纯 Base64 数据
        if "," in base64_data:
            base64_data = base64_data.split(",")[1]

        import base64

        data = base64.b64decode(base64_data)

        mime_map = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "webp": "image/webp",
            "gif": "image/gif",
            "mp4": "video/mp4",
            "webm": "video/webm",
            "mp3": "audio/mpeg",
            "wav": "audio/wav",
            "pdf": "application/pdf",
            "svg": "image/svg+xml",
        }
        mime = mime_map.get(ext, "application/octet-stream")

        return await self.upload(
            data=data,
            mime=mime,
            category=category,
            owner_id=owner_id,
            ext=ext,
            storage_class=storage_class,
            suggested_name=suggested_name,
        )

    async def get_presigned_upload_url(
        self,
        category: str,
        owner_id: str,
        mime: str,
        ext: str,
        *,
        storage_class: StorageClass = StorageClass.BUFFER,
        expires_in: int = 600,
        suggested_name: str | None = None,
    ) -> PresignedUrlResult:
        """生成预签名上传 URL（客户端直接上传到 R2）。

        Args:
            category: 内容类别。
            owner_id: 所有者 ID。
            mime: MIME 类型。
            ext: 文件扩展名。
            storage_class: 存储类别。
            expires_in: URL 过期时间（秒），默认 600。
            suggested_name: 可读文件名。

        Returns:
            PresignedUrlResult 包含 upload_url、key、public_url。
        """

        client = self._get_client()
        is_permanent = storage_class == StorageClass.PERMANENT
        bucket = self._config.get_bucket(permanent=is_permanent)

        key = generate_r2_key(
            category=category,
            owner_id=owner_id,
            ext=ext,
            suggested_name=suggested_name,
        )

        cache_control = "public, max-age=31536000, immutable" if is_permanent else "public, max-age=86400"

        try:
            presigned_url = client.generate_presigned_url(
                ClientMethod="put_object",
                Params={
                    "Bucket": bucket,
                    "Key": key,
                    "ContentType": mime,
                    "CacheControl": cache_control,
                },
                ExpiresIn=expires_in,
            )
        except Exception as e:
            logger.error("R2 presigned URL generation failed: %s", e)
            raise RuntimeError(f"Failed to generate presigned URL: {e}") from e

        public_url = self._config.build_cdn_url(key, permanent=is_permanent)

        return PresignedUrlResult(
            upload_url=presigned_url,
            key=key,
            public_url=public_url,
            expires_in=expires_in,
        )

    async def delete(self, key: str, *, permanent: bool = False) -> DeleteResult:
        """从 R2 删除对象。

        Args:
            key: 对象 key。
            permanent: 是否从永久桶删除（否则从 buffer 桶）。

        Returns:
            DeleteResult。
        """
        client = self._get_client()
        bucket = self._config.get_bucket(permanent=permanent)

        try:
            client.delete_object(Bucket=bucket, Key=key)
            logger.info("R2 delete success (bucket=%s, key=%s)", bucket, key)
            return DeleteResult(success=True, key=key)
        except Exception as e:
            logger.error("R2 delete failed (bucket=%s, key=%s): %s", bucket, key, e)
            return DeleteResult(success=False, key=key, error=str(e))

    async def status(self) -> StorageStatus:
        """检查 R2 连接状态。

        Returns:
            StorageStatus 包含可用性、桶信息。
        """
        if not _boto3_available:
            return StorageStatus(
                available=False,
                error="boto3 is not installed. Install with: pip install boto3",
            )
        if not self._config.is_configured:
            return StorageStatus(
                available=False,
                error="R2 is not configured. Set R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ENDPOINT, and R2_BUCKET_BUFFER",
            )

        try:
            client = self._get_client()
            # 尝试列出 buffer 桶来验证连接
            client.list_objects_v2(Bucket=self._config.buffer_bucket, MaxKeys=1)
            return StorageStatus(
                available=True,
                buffer_bucket=self._config.buffer_bucket,
                permanent_bucket=self._config.permanent_bucket,
                buffer_cdn=self._config.buffer_cdn_url,
                permanent_cdn=self._config.permanent_cdn_url,
            )
        except Exception as e:
            logger.warning("R2 status check failed: %s", e)
            return StorageStatus(
                available=False,
                buffer_bucket=self._config.buffer_bucket,
                permanent_bucket=self._config.permanent_bucket,
                error=str(e),
            )

    async def list_objects(
        self,
        prefix: str,
        max_keys: int = 100,
        *,
        permanent: bool = False,
    ) -> list[dict]:
        """列出 R2 对象。

        Args:
            prefix: key 前缀过滤。
            max_keys: 最大返回数量。
            permanent: 是否查询永久桶。

        Returns:
            对象信息列表 [{key, size, last_modified, url}, ...]。
        """
        client = self._get_client()
        bucket = self._config.get_bucket(permanent=permanent)

        try:
            response = client.list_objects_v2(
                Bucket=bucket,
                Prefix=prefix,
                MaxKeys=max_keys,
            )
            objects = []
            for obj in response.get("Contents", []):
                key = obj.get("Key", "")
                objects.append(
                    {
                        "key": key,
                        "size": obj.get("Size", 0),
                        "last_modified": obj.get("LastModified").isoformat() if obj.get("LastModified") else None,
                        "url": self._config.build_cdn_url(key, permanent=permanent),
                    }
                )
            return objects
        except Exception as e:
            logger.error("R2 list objects failed (bucket=%s, prefix=%s): %s", bucket, prefix, e)
            return []


# ─── 全局客户端 ─────────────────────────────────────────────────────────

_client: R2Client | None = None


def get_r2_client() -> R2Client:
    """获取全局 R2 客户端（惰性初始化）。"""
    global _client
    if _client is None:
        _client = R2Client()
    return _client


# ─── 便捷函数（默认使用全局客户端） ──────────────────────────────────────


async def upload_to_r2(
    data: bytes,
    mime: str,
    category: str,
    owner_id: str,
    ext: str,
    *,
    storage_class: StorageClass = StorageClass.BUFFER,
    suggested_name: str | None = None,
    key_override: str | None = None,
) -> UploadResult:
    """上传文件到 R2（便捷函数，使用全局客户端）。"""
    return await get_r2_client().upload(
        data=data,
        mime=mime,
        category=category,
        owner_id=owner_id,
        ext=ext,
        storage_class=storage_class,
        suggested_name=suggested_name,
        key_override=key_override,
    )


async def upload_base64_to_r2(
    base64_data: str,
    category: str,
    owner_id: str,
    ext: str,
    *,
    storage_class: StorageClass = StorageClass.BUFFER,
    suggested_name: str | None = None,
) -> UploadResult:
    """上传 Base64 数据到 R2（便捷函数，使用全局客户端）。"""
    return await get_r2_client().upload_base64(
        base64_data=base64_data,
        category=category,
        owner_id=owner_id,
        ext=ext,
        storage_class=storage_class,
        suggested_name=suggested_name,
    )


async def get_presigned_upload_url(
    category: str,
    owner_id: str,
    mime: str,
    ext: str,
    *,
    storage_class: StorageClass = StorageClass.BUFFER,
    expires_in: int = 600,
    suggested_name: str | None = None,
) -> PresignedUrlResult:
    """生成预签名上传 URL（便捷函数，使用全局客户端）。"""
    return await get_r2_client().get_presigned_upload_url(
        category=category,
        owner_id=owner_id,
        mime=mime,
        ext=ext,
        storage_class=storage_class,
        expires_in=expires_in,
        suggested_name=suggested_name,
    )


async def delete_from_r2(
    key: str,
    *,
    permanent: bool = False,
) -> DeleteResult:
    """从 R2 删除对象（便捷函数，使用全局客户端）。"""
    return await get_r2_client().delete(key=key, permanent=permanent)


async def get_r2_status() -> StorageStatus:
    """检查 R2 连接状态（便捷函数，使用全局客户端）。"""
    return await get_r2_client().status()


async def list_r2_objects(
    prefix: str,
    max_keys: int = 100,
    *,
    permanent: bool = False,
) -> list[dict]:
    """列出 R2 对象（便捷函数，使用全局客户端）。"""
    return await get_r2_client().list_objects(
        prefix=prefix,
        max_keys=max_keys,
        permanent=permanent,
    )
