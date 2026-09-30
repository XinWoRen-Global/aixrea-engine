"""DeerFlow 统一存储层 — 数据模型。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal


class StorageBackend(StrEnum):
    """支持的存储后端。"""

    R2 = "r2"
    LOCAL = "local"


class StorageClass(StrEnum):
    """存储类别：buffer（临时，30天过期）或 permanent（永久）。"""

    BUFFER = "buffer"
    PERMANENT = "permanent"


@dataclass
class StorageRoute:
    """存储路由决策结果。"""

    storage_class: StorageClass
    bucket_name: str
    cdn_base_url: str
    content_category: str
    expires_at: datetime | None = None

    @property
    def is_permanent(self) -> bool:
        return self.storage_class == StorageClass.PERMANENT


@dataclass
class UploadResult:
    """R2 上传结果。"""

    key: str
    url: str
    size: int
    bucket_name: str
    storage_class: StorageClass
    success: bool = True
    error: str | None = None


@dataclass
class PresignedUrlResult:
    """预签名上传 URL 结果。"""

    upload_url: str
    key: str
    public_url: str
    expires_in: int = 600


@dataclass
class DeleteResult:
    """R2 删除结果。"""

    success: bool
    key: str
    error: str | None = None


@dataclass
class StorageStatus:
    """R2 存储连接状态。"""

    available: bool
    buffer_bucket: str | None = None
    permanent_bucket: str | None = None
    buffer_cdn: str | None = None
    permanent_cdn: str | None = None
    error: str | None = None


# ─── 文件类别（与前端 ContentCategory 对齐） ─────────────────────────────

# 与前端 src/lib/storage/r2-client.ts 的 ContentCategory 类型保持一致
ContentCategory = Literal[
    "video",
    "video/segment",
    "reels",
    "image",
    "audio",
    "document",
    "canvas",
    "product",
    "avatar",
    "temp",
    "music",
    "script",
    "interactive",
    "comic",
    "kyc",
    "asset",
    "service",
    "blog",
    "admin",
]

# 草稿类目（走 d/ 前缀，含 ownerId，30天自动删除）
DRAFT_CATEGORIES: set[str] = {
    "video",
    "video/segment",
    "image",
    "audio",
    "canvas",
    "temp",
}


def is_draft_category(category: str) -> bool:
    """判断是否草稿类目（走 d/ 前缀，30天过期）。"""
    return category in DRAFT_CATEGORIES


def generate_r2_key(
    category: str,
    owner_id: str,
    ext: str,
    *,
    suggested_name: str | None = None,
) -> str:
    """生成 R2 object key，与前端 generateKey() 逻辑保持一致。

    草稿类（d/ 前缀）：d/{owner_id}/{rand}.{ext} 或 d/{owner_id}/{date}_{name}.{ext}
    永久类（p/ 前缀）：p/{category}/{owner_id}/{hash}.{ext} 或 p/{category}/{owner_id}/{date}_{name}.{ext}
    """
    import hashlib
    import random
    import string
    from datetime import date

    today = date.today().isoformat()  # YYYY-MM-DD
    clean_name = _sanitize_name(suggested_name) if suggested_name else ""

    if is_draft_category(category):
        # 草稿类：d/{ownerId}/{fileBase}.{ext}
        if clean_name:
            file_base = f"{today}_{clean_name}"
        else:
            file_base = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
        return f"d/{owner_id}/{file_base}.{ext}"

    # 永久类：p/{category}/{ownerId}/{fileBase}.{ext}
    if clean_name:
        file_base = f"{today}_{clean_name}"
    else:
        # 内容哈希，与前端 sha256 一致
        raw = f"{owner_id}:{category}:{random.random()}".encode()
        file_base = hashlib.sha256(raw).hexdigest()[:8]
    return f"p/{category}/{owner_id}/{file_base}.{ext}"


def _sanitize_name(name: str) -> str:
    """清理文件名，与前端 sanitizeName() 逻辑保持一致。"""
    import re

    # 只保留字母数字、CJK、连字符、下划线、点
    cleaned = re.sub(r"[^\w\s\-一-鿿\.]", "-", name, flags=re.UNICODE)
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    cleaned = cleaned.strip("-")
    return cleaned[:80] if cleaned else "file"
