"""
配置持久化模块 — 从数据库加载/保存 API 渠道配置，支持版本管理和回滚。

大厂做法：
1. 后端启动时从数据库加载配置（api_channels 表）
2. 配置变更时自动保存到数据库
3. 配置版本管理和回滚（api_config_versions 表）

SSOT：数据库是配置的唯一真实来源，运行时缓存只是加速层。
"""

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

from httpx import AsyncClient

logger = logging.getLogger("config.persistence")

# ── 配置缓存 ──────────────────────────────────────────────────────────────
_config_cache: dict[str, Any] = {
    "channels": [],
    "model_mappings": [],
    "last_loaded": None,
    "version": None,
}


# ── 数据库连接 ────────────────────────────────────────────────────────────
def _get_db_config() -> tuple[str, str]:
    """获取数据库连接配置"""
    url = os.environ.get("NEXT_PUBLIC_INSFORGE_URL", "")
    service_key = os.environ.get("INSFORGE_SERVICE_ROLE_KEY", "")
    if not url or not service_key:
        raise RuntimeError("InsForge 配置缺失，环境变量未设置: NEXT_PUBLIC_INSFORGE_URL, INSFORGE_SERVICE_ROLE_KEY")
    return url, service_key


async def _request(method: str, path: str, **kwargs) -> dict:
    """发送请求到 PostgREST API"""
    url, service_key = _get_db_config()
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    headers.update(kwargs.pop("headers", {}))

    async with AsyncClient(timeout=30.0) as client:
        response = await client.request(
            method,
            f"{url}/api/database/records{path}",
            headers=headers,
            **kwargs,
        )
        response.raise_for_status()
        if response.status_code == 204:
            return {}
        return response.json()


# ── 配置加载 ──────────────────────────────────────────────────────────────
async def load_channels_from_db() -> list[dict]:
    """从数据库加载所有 active 的 API 渠道配置"""
    try:
        result = await _request(
            "GET",
            "/api_channels",
            params={"select": "id,name,provider,base_url,api_key_encrypted,priority,rate_limit_rpm,monthly_quota,status,health_status,notes,created_at,updated_at", "status": "eq.active", "order": "priority.asc"},
        )
        logger.info(f"[config] 从数据库加载 {len(result)} 个 API 渠道配置")
        return result
    except Exception as e:
        logger.error(f"[config] 从数据库加载 API 渠道配置失败: {e}")
        return []


async def load_model_mappings_from_db() -> list[dict]:
    """从数据库加载所有 active 的模型映射配置"""
    try:
        result = await _request(
            "GET",
            "/api_model_mappings",
            params={"select": "id,capability,model_name,model_family,credits_per_unit,unit_type,priority,is_active,allow_degradation,channel_id", "is_active": "eq.true", "order": "capability.asc,priority.asc"},
        )
        logger.info(f"[config] 从数据库加载 {len(result)} 个模型映射配置")
        return result
    except Exception as e:
        logger.error(f"[config] 从数据库加载模型映射配置失败: {e}")
        return []


async def load_all_config_from_db() -> dict[str, Any]:
    """从数据库加载所有配置（渠道 + 模型映射）"""
    channels = await load_channels_from_db()
    model_mappings = await load_model_mappings_from_db()

    _config_cache["channels"] = channels
    _config_cache["model_mappings"] = model_mappings
    _config_cache["last_loaded"] = datetime.now(UTC).isoformat()

    logger.info(f"[config] 配置加载完成：{len(channels)} 个渠道，{len(model_mappings)} 个模型映射")
    return _config_cache


# ── 配置保存 ──────────────────────────────────────────────────────────────
async def save_config_version(
    config_type: str,
    config_data: dict,
    description: str = "",
    created_by: str = "system",
) -> dict:
    """保存配置版本（用于版本管理和回滚）

    Args:
        config_type: 配置类型（channels / model_mappings / all）
        config_data: 配置数据（JSON 序列化）
        description: 版本描述
        created_by: 创建者

    Returns:
        保存的版本记录
    """
    try:
        version_data = {
            "config_type": config_type,
            "config_data": json.dumps(config_data, ensure_ascii=False),
            "description": description,
            "created_by": created_by,
            "created_at": datetime.now(UTC).isoformat(),
        }
        result = await _request(
            "POST",
            "/api_config_versions",
            json=version_data,
        )
        logger.info(f"[config] 保存配置版本：{config_type} - {description}")
        return result[0] if isinstance(result, list) else result
    except Exception as e:
        logger.error(f"[config] 保存配置版本失败: {e}")
        return {}


async def get_config_versions(config_type: str = None, limit: int = 20) -> list[dict]:
    """获取配置版本列表

    Args:
        config_type: 配置类型（可选，不传则返回所有类型）
        limit: 返回数量限制

    Returns:
        配置版本列表
    """
    try:
        params = {"select": "*", "order": "created_at.desc", "limit": limit}
        if config_type:
            params["config_type"] = f"eq.{config_type}"
        result = await _request("GET", "/api_config_versions", params=params)
        return result
    except Exception as e:
        logger.error(f"[config] 获取配置版本列表失败: {e}")
        return []


async def rollback_to_version(version_id: int) -> dict:
    """回滚到指定配置版本

    Args:
        version_id: 版本 ID

    Returns:
        回滚结果
    """
    try:
        # 获取指定版本
        versions = await _request(
            "GET",
            "/api_config_versions",
            params={"id": f"eq.{version_id}", "limit": 1},
        )
        if not versions:
            raise ValueError(f"配置版本 {version_id} 不存在")

        version = versions[0]
        config_data = json.loads(version["config_data"])
        config_type = version["config_type"]

        # 根据配置类型恢复（同步到运行时，数据库表更新需要前端配合）
        # 注意：完整的回滚需要更新数据库表（api_channels / api_model_mappings）
        # 这里先实现运行时回滚，数据库表更新可以通过前端重新同步实现
        if config_type in ("channels", "all"):
            # 将渠道配置同步到运行时
            providers = config_data.get("providers", {})
            env = config_data.get("env", {})
            if providers or env:
                from app.gateway.routers.ai_proxy import pool

                pool.sync_keys(env, providers)
                logger.info(f"[config] 渠道配置已回滚到运行时（版本 {version_id}）")
        if config_type in ("model_mappings", "all"):
            # 将模型映射配置同步到运行时
            mappings = config_data.get("mappings", [])
            if mappings:
                from app.gateway.routers.ai_proxy import RUNTIME_MODEL_MAPPINGS

                RUNTIME_MODEL_MAPPINGS.clear()
                RUNTIME_MODEL_MAPPINGS.extend(mappings)
                logger.info(f"[config] 模型映射配置已回滚到运行时（版本 {version_id}）")

        # 记录回滚操作
        await save_config_version(
            config_type=config_type,
            config_data=config_data,
            description=f"回滚到版本 {version_id}",
            created_by="system",
        )

        return {"success": True, "version_id": version_id, "config_type": config_type}
    except Exception as e:
        logger.error(f"[config] 回滚配置版本失败: {e}")
        return {"success": False, "error": str(e)}


# ── 配置同步到运行时 ──────────────────────────────────────────────────────
async def sync_config_to_runtime() -> dict:
    """从数据库加载配置并同步到运行时

    注意：API Key 是加密存储在数据库中的（api_key_encrypted 字段），
    后端没有解密密钥，因此 API Key 仍然从环境变量加载。
    从数据库加载的配置主要用于：
    1. BaseURL 动态配置（支持后台修改 BaseURL）
    2. 模型映射配置（api_model_mappings 表）
    3. 配置版本管理和审计

    完整的配置同步流程：
    1. 前端从数据库加载配置，解密 API Key
    2. 前端调用后端 /api/ai/providers/sync-keys 端点，传递解密后的 API Key
    3. 后端保存配置版本到数据库（用于审计和回滚）

    Returns:
        同步结果
    """
    from app.gateway.routers.ai_proxy import RUNTIME_MODEL_MAPPINGS, pool

    # 加载配置
    config = await load_all_config_from_db()
    channels = config["channels"]
    model_mappings = config["model_mappings"]

    # 从数据库加载 BaseURL 配置（API Key 从环境变量加载）
    provider_base_urls: dict[str, str] = {}
    for channel in channels:
        provider = channel.get("provider", "").lower()
        base_url = channel.get("base_url", "")
        if provider and base_url:
            # 确保 BaseURL 以 /chat/completions 结尾
            if not base_url.endswith("/chat/completions"):
                base_url = base_url.rstrip("/") + "/chat/completions"
            provider_base_urls[provider] = base_url

    # 从环境变量加载 API Key
    env_vars: dict[str, str] = {}
    PROVIDER_ENV_MAP = {
        "nvidia": "NVIDIA_API_KEYS",
        "groq": "GROQ_API_KEYS",
        "siliconflow": "SILICONFLOW_API_KEYS",
        "openrouter": "OPENROUTER_API_KEYS",
        "bailian": "BAILIAN_API_KEYS",
        "bailian2": "BAILIAN2_API_KEYS",
        "bailian3": "BAILIAN3_API_KEYS",
        "bailian4": "BAILIAN4_API_KEYS",
        "bailian5": "BAILIAN5_API_KEYS",
        "seedance2": "SEEDANCE2_API_KEYS",
        "agnes": "AGNES_API_KEYS",
    }

    for prov, env_key in PROVIDER_ENV_MAP.items():
        api_keys = os.environ.get(env_key, "")
        if api_keys:
            env_vars[env_key] = api_keys

    # 构建 provider 配置（BaseURL 从数据库，API Key 从环境变量）
    providers: dict[str, dict] = {}
    for prov, base_url in provider_base_urls.items():
        env_key = PROVIDER_ENV_MAP.get(prov)
        api_keys = env_vars.get(env_key, "")
        providers[prov] = {
            "api_keys": [k.strip() for k in api_keys.split(",") if k.strip()],
            "base_url": base_url,
        }

    # 同步到运行时
    count = pool.sync_keys(env_vars, providers)

    # 同步模型映射
    if model_mappings:
        RUNTIME_MODEL_MAPPINGS.clear()
        RUNTIME_MODEL_MAPPINGS.extend(model_mappings)

    logger.info(f"[config] 配置同步到运行时：{count} 个 provider，{len(model_mappings)} 个模型映射，{len(provider_base_urls)} 个 BaseURL 从数据库加载")
    return {
        "success": True,
        "providers_synced": count,
        "model_mappings_synced": len(model_mappings),
        "channels_loaded": len(channels),
        "base_urls_from_db": len(provider_base_urls),
    }


# ── 配置缓存访问 ──────────────────────────────────────────────────────────
def get_cached_config() -> dict:
    """获取缓存的配置"""
    return _config_cache


def get_cached_channels() -> list[dict]:
    """获取缓存的渠道配置"""
    return _config_cache["channels"]


def get_cached_model_mappings() -> list[dict]:
    """获取缓存的模型映射配置"""
    return _config_cache["model_mappings"]
