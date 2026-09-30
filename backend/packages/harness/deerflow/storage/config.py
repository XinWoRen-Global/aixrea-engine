"""DeerFlow 统一存储层 — R2 配置（从环境变量读取）。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Self


@dataclass
class R2Config:
    """Cloudflare R2 S3-compatible 存储配置。

    从环境变量读取，与前端 src/lib/storage/r2-client.ts 的配置来源一致。
    """

    endpoint_url: str = ""
    access_key_id: str = ""
    secret_access_key: str = ""
    buffer_bucket: str = "xinworen-buffer"
    permanent_bucket: str = "xinworen-permanent"
    buffer_cdn_url: str = ""
    permanent_cdn_url: str = ""
    buffer_days: int = 30
    max_upload_bytes: int = 500 * 1024 * 1024  # 500MB

    @classmethod
    def from_env(cls) -> Self:
        """从环境变量读取 R2 配置。"""
        buffer_bucket = os.environ.get("R2_BUCKET_BUFFER", "xinworen-buffer")
        permanent_bucket = os.environ.get("R2_BUCKET_PERMANENT", "") or buffer_bucket
        endpoint_url = os.environ.get(
            "R2_ENDPOINT",
            "https://<account_id>.r2.cloudflarestorage.com",
        )
        access_key_id = os.environ.get("R2_ACCESS_KEY_ID", "")
        secret_access_key = os.environ.get("R2_SECRET_ACCESS_KEY", "")
        buffer_cdn = os.environ.get("R2_CDN_BUFFER_URL", "")
        permanent_cdn = os.environ.get("R2_CDN_PERMANENT_URL", "") or buffer_cdn
        buffer_days = int(os.environ.get("R2_BUFFER_DAYS", "30"))
        max_mb = int(os.environ.get("R2_MAX_UPLOAD_MB", "500"))

        return cls(
            endpoint_url=endpoint_url,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            buffer_bucket=buffer_bucket,
            permanent_bucket=permanent_bucket,
            buffer_cdn_url=buffer_cdn,
            permanent_cdn_url=permanent_cdn,
            buffer_days=buffer_days,
            max_upload_bytes=max_mb * 1024 * 1024,
        )

    @property
    def is_configured(self) -> bool:
        """检查 R2 配置是否完整（有 endpoint + 凭证 + 至少一个桶）。"""
        return bool(self.endpoint_url and self.access_key_id and self.secret_access_key and self.buffer_bucket)

    def get_bucket(self, *, permanent: bool = False) -> str:
        """获取桶名。"""
        return self.permanent_bucket if permanent else self.buffer_bucket

    def get_cdn_url(self, *, permanent: bool = False) -> str:
        """获取 CDN URL。"""
        return self.permanent_cdn_url if permanent else self.buffer_cdn_url

    def build_cdn_url(self, key: str, *, permanent: bool = False) -> str:
        """根据 key 构建完整的 CDN URL。"""
        cdn = self.get_cdn_url(permanent=permanent)
        if not cdn:
            bucket = self.get_bucket(permanent=permanent)
            return f"https://{bucket}.r2.cloudflarestorage.com/{key}"
        return f"{cdn.rstrip('/')}/{key}"


# 全局单例
_r2_config: R2Config | None = None


def get_r2_config() -> R2Config:
    """获取全局 R2 配置（惰性初始化）。"""
    global _r2_config
    if _r2_config is None:
        _r2_config = R2Config.from_env()
    return _r2_config


def reload_r2_config() -> R2Config:
    """重新加载 R2 配置（环境变量变化后调用）。"""
    global _r2_config
    _r2_config = R2Config.from_env()
    return _r2_config
