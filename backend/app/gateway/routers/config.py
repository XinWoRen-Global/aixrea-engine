"""
配置中心 API — 大厂标准做法
- GET  /api/config              获取所有公开配置
- GET  /api/config/{key}        获取单个配置
- PUT  /api/config/{key}        更新配置（管理员）
- POST /api/config/reload       重新加载配置（从 DB 刷新内存缓存）

存储层级：
1. InsForge DB (app_config 表) — 持久化，运行时可修改
2. 内存缓存 — 避免每次请求都查 DB
3. 环境变量 — 兜底默认值
"""

import asyncio
import logging
import os
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.gateway.deps import require_admin_user
from app.gateway.pipeline_insforge import _request

logger = logging.getLogger(__name__)
router = APIRouter(tags=["config"])

_ADMIN_REQUIRED_DETAIL = "Admin privileges required to modify gateway configuration."

# 内存缓存
_config_cache: dict[str, Any] = {}
_cache_loaded = False
_cache_last_refresh: float = 0
_CACHE_TTL_SECONDS = 300  # 5 分钟自动刷新
_cache_refresh_lock = asyncio.Lock()


class ConfigUpdateRequest(BaseModel):
    """配置更新请求"""

    value: Any
    description: str | None = None


def _load_config_from_env() -> dict[str, Any]:
    """从环境变量加载默认配置（兜底）"""
    return {
        "ai.gateway.enabled": True,
        "ai.gateway.timeout_seconds": 30,
        "ai.gateway.retry_count": 2,
        "byok.enabled": True,
        "byok.stats_store": os.getenv("BYOK_STATS_STORE", "file"),
        "byok.encryption_enabled": True,
        "payment.antom.enabled": True,
        "payment.paypal.enabled": True,
        "payment.mode": os.getenv("PAYMENT_MODE", "phase1"),
        "moderation.enabled": True,
        "moderation.provider": "llm",
        "moderation.auto_block": True,
        "feature.pwa_enabled": True,
        "feature.i18n_enabled": True,
        "feature.marketplace_enabled": True,
        "feature.studio_enabled": True,
        "feature.drama_enabled": True,
        "general.site_name": "新我人 XinWoRen",
        "general.site_url": "https://xinworen.com",
        "general.default_locale": "zh",
        "general.support_email": "support@xinworen.com",
    }


async def _load_config_from_db() -> dict[str, Any]:
    """从 InsForge DB 加载配置（app_config 表）"""
    try:
        # 查询所有公开配置（is_public=true）
        results = await _request(
            "GET",
            "app_config",
            query={"is_public": "eq.true", "select": "config_key,config_value,config_type,description,category,updated_at"},
        )
        if not results:
            logger.info("app_config table empty or not found, falling back to env defaults")
            return {}

        config: dict[str, Any] = {}
        for row in results:
            key = row.get("config_key")
            value = row.get("config_value")
            if key and value is not None:
                # PostgREST 返回的 JSONB 可能是字符串，需要解析
                if isinstance(value, str):
                    try:
                        import json

                        value = json.loads(value)
                    except (json.JSONDecodeError, TypeError):
                        pass  # 保持原始字符串
                config[key] = value

        logger.info(f"Loaded {len(config)} config items from InsForge DB")
        return config
    except Exception as e:
        logger.warning(f"Failed to load config from DB: {e}, falling back to env defaults")
        return {}


async def _save_config_to_db(config_key: str, value: Any, description: str | None = None) -> bool:
    """保存配置到 InsForge DB（upsert）"""
    try:
        import json

        # 先查询是否存在
        existing = await _request(
            "GET",
            "app_config",
            query={"config_key": f"eq.{config_key}", "select": "id"},
        )

        config_value = json.dumps(value, ensure_ascii=False)
        config_type = "json" if isinstance(value, (dict, list)) else type(value).__name__

        if existing:
            # 更新
            await _request(
                "PATCH",
                "app_config",
                query={"config_key": f"eq.{config_key}"},
                body={
                    "config_value": config_value,
                    "config_type": config_type,
                    "description": description or existing[0].get("description", ""),
                    "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                },
            )
        else:
            # 插入
            await _request(
                "POST",
                "app_config",
                body={
                    "config_key": config_key,
                    "config_value": config_value,
                    "config_type": config_type,
                    "description": description or "",
                    "category": "general",
                    "is_public": True,
                    "is_encrypted": False,
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                },
            )

        logger.info(f"Config saved to DB: {config_key} = {value}")
        return True
    except Exception as e:
        logger.error(f"Failed to save config to DB: {e}")
        return False


async def _get_config_cache(force_refresh: bool = False) -> dict[str, Any]:
    """获取配置缓存（懒加载 + 自动刷新）"""
    global _cache_loaded, _config_cache, _cache_last_refresh

    now = time.time()
    needs_refresh = force_refresh or not _cache_loaded or (now - _cache_last_refresh > _CACHE_TTL_SECONDS)

    if needs_refresh:
        # 加锁避免并发首载/刷新时重复打 DB（asyncio.Lock 按事件循环创建，模块级单例在单 loop 下安全）
        async with _cache_refresh_lock:
            now = time.time()
            needs_refresh = force_refresh or not _cache_loaded or (now - _cache_last_refresh > _CACHE_TTL_SECONDS)
            if needs_refresh:
                # 从 DB 加载，合并 env 默认值
                db_config = await _load_config_from_db()
                env_config = _load_config_from_env()
                # DB 配置优先，env 作为兜底
                _config_cache = {**env_config, **db_config}
                _cache_loaded = True
                _cache_last_refresh = now
                logger.info(f"Config cache refreshed: {len(_config_cache)} items (source: db+env)")

    return _config_cache


@router.get("/api/config")
async def get_all_config() -> dict[str, Any]:
    """获取所有公开配置（前端可直接使用）"""
    config = await _get_config_cache()
    return {
        "config": config,
        "count": len(config),
        "source": "db+env",
        "last_refresh": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(_cache_last_refresh)) if _cache_last_refresh else None,
        "cache_ttl_seconds": _CACHE_TTL_SECONDS,
    }


@router.get("/api/config/{config_key}")
async def get_config(config_key: str) -> dict[str, Any]:
    """获取单个配置"""
    config = await _get_config_cache()
    if config_key not in config:
        raise HTTPException(status_code=404, detail=f"Config key '{config_key}' not found")
    return {
        "key": config_key,
        "value": config[config_key],
        "source": "db+env",
    }


@router.put("/api/config/{config_key}")
async def update_config(config_key: str, body: ConfigUpdateRequest, request: Request) -> dict[str, Any]:
    """更新配置（管理员权限）"""
    await require_admin_user(request, detail=_ADMIN_REQUIRED_DETAIL)
    global _config_cache

    # 保存到 DB
    db_saved = await _save_config_to_db(config_key, body.value, body.description)

    # 更新内存缓存
    config = await _get_config_cache()
    config[config_key] = body.value

    logger.info(f"Config updated: {config_key} = {body.value} (db_saved={db_saved})")

    return {
        "success": True,
        "key": config_key,
        "value": body.value,
        "db_persisted": db_saved,
        "note": "已更新内存缓存" + ("并持久化到 InsForge DB" if db_saved else "，DB 持久化失败（表可能未创建）"),
    }


@router.post("/api/config/reload")
async def reload_config(request: Request) -> dict[str, Any]:
    """重新加载配置（强制从 DB 刷新内存缓存，管理员权限）"""
    await require_admin_user(request, detail=_ADMIN_REQUIRED_DETAIL)
    config = await _get_config_cache(force_refresh=True)
    return {
        "success": True,
        "reloaded": True,
        "config_count": len(config),
        "source": "db+env",
        "last_refresh": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(_cache_last_refresh)),
    }
