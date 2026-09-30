"""
Large Output Cache — 大输出本地缓存（参考 SoL-Pi 机制 #2）

AI 生成的长文本（剧本、歌词）在后续步骤中被重复读取，每次都占 context。
做法：
- 大输出（>500 tokens）写入 Redis 缓存，返回引用 ID
- 后续步骤需要时按需加载，不全部塞进 context
- 配合 RAG 式检索，只取相关片段

预期收益：多步骤创作任务 token 降低 25-35%

参考：https://github.com/NVlabs/SoL-Pi
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

logger = logging.getLogger("large_output_cache")

# 缓存配置
CACHE_THRESHOLD_TOKENS = 500  # 超过此 tokens 的输出才缓存
CACHE_TTL_SECONDS = 86400 * 7  # 缓存 7 天
CACHE_KEY_PREFIX = "large_output:"

# 全局 Redis 客户端（懒初始化）
_redis_client = None


def _get_redis():
    """获取 Redis 客户端（懒初始化）。"""
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    try:
        import os

        redis_url = os.environ.get("REDIS_URL") or os.environ.get("REDIS_CONNECTION_STRING")
        if redis_url:
            import redis.asyncio as aioredis

            _redis_client = aioredis.from_url(redis_url, decode_responses=True)
            logger.info("LargeOutputCache redis initialized")
        else:
            logger.warning("REDIS_URL not set, large output cache disabled")
    except Exception as e:
        logger.warning("LargeOutputCache redis init failed: %s", e)
        _redis_client = None

    return _redis_client


def _make_cache_key(content: str, namespace: str = "default") -> str:
    """生成缓存 key（内容哈希 + 命名空间）。"""
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    return f"{CACHE_KEY_PREFIX}{namespace}:{content_hash}"


def estimate_tokens(text: str) -> int:
    """粗略估算 token 数。"""
    if not text:
        return 0
    import re

    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    other_chars = len(text) - chinese_chars
    return int(chinese_chars / 1.5 + other_chars / 4)


async def cache_large_output(
    content: str,
    namespace: str = "default",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """缓存大输出，返回引用信息。

    如果内容小于阈值，不缓存，直接返回原内容。

    Args:
        content: 要缓存的内容
        namespace: 命名空间（如 drama_script, music_lyrics）
        metadata: 元数据

    Returns:
        缓存信息：{cached, cache_key, content_ref, original_tokens, metadata}
    """
    tokens = estimate_tokens(content)

    if tokens < CACHE_THRESHOLD_TOKENS:
        return {
            "cached": False,
            "cache_key": None,
            "content_ref": None,
            "original_tokens": tokens,
            "content": content,
        }

    cache_key = _make_cache_key(content, namespace)
    redis = _get_redis()

    if redis:
        try:
            import json

            payload = {
                "content": content,
                "tokens": tokens,
                "namespace": namespace,
                "metadata": metadata or {},
                "created_at": time.time(),
            }
            await redis.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(payload, ensure_ascii=False))
            logger.info(
                "Large output cached: key=%s tokens=%d namespace=%s",
                cache_key,
                tokens,
                namespace,
            )
        except Exception as e:
            logger.warning("Cache large output failed: %s", e)

    return {
        "cached": True,
        "cache_key": cache_key,
        "content_ref": f"[cached:{namespace}:{cache_key[-8:]}]",
        "original_tokens": tokens,
        "metadata": metadata or {},
    }


async def get_cached_output(cache_key: str) -> dict[str, Any] | None:
    """获取缓存的大输出。

    Args:
        cache_key: 缓存 key

    Returns:
        缓存内容，None 表示未命中
    """
    redis = _get_redis()
    if not redis:
        return None

    try:
        import json

        raw = await redis.get(cache_key)
        if raw:
            return json.loads(raw)
    except Exception as e:
        logger.warning("Get cached output failed: %s", e)

    return None


async def get_cached_output_summary(cache_key: str, max_chars: int = 200) -> str:
    """获取缓存内容的摘要（用于上下文引用）。

    Args:
        cache_key: 缓存 key
        max_chars: 摘要最大字符数

    Returns:
        摘要文本
    """
    cached = await get_cached_output(cache_key)
    if not cached:
        return "[缓存未命中]"

    content = cached.get("content", "")
    tokens = cached.get("tokens", 0)

    if len(content) <= max_chars:
        return content

    return content[:max_chars] + f"...[共 {tokens} tokens，完整内容见缓存 {cache_key[-8:]}]"


def should_cache(content: str) -> bool:
    """判断是否应该缓存。"""
    return estimate_tokens(content) >= CACHE_THRESHOLD_TOKENS


async def get_cache_stats() -> dict[str, Any]:
    """获取缓存统计（用于监控）。"""
    redis = _get_redis()
    if not redis:
        return {"enabled": False}

    try:
        keys = await redis.keys(f"{CACHE_KEY_PREFIX}*")
        return {
            "enabled": True,
            "cached_items": len(keys),
            "threshold_tokens": CACHE_THRESHOLD_TOKENS,
            "ttl_seconds": CACHE_TTL_SECONDS,
        }
    except Exception as e:
        return {"enabled": True, "error": str(e)}
