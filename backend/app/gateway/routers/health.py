"""
综合健康检查端点 — 大厂标准做法
- /api/health          综合健康检查（含 DB、AI网关、BYOK、系统资源）
- /api/health/live     存活探针（K8s liveness）
- /api/health/ready    就绪探针（K8s readiness）
- /api/health/metrics  关键指标摘要
"""

import logging
import os
import time
from typing import Any

from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])

# 服务启动时间（用于计算 uptime）
_START_TIME = time.time()


def _get_uptime_seconds() -> float:
    """计算服务运行时长（秒）"""
    return time.time() - _START_TIME


def _check_insforge_db() -> dict[str, Any]:
    """检查 InsForge DB 连接状态（轻量探测，不实际查询）"""
    insforge_url = os.getenv("NEXT_PUBLIC_INSFORGE_URL", "") or os.getenv("INSFORGE_URL", "")
    has_service_key = bool(os.getenv("INSFORGE_SERVICE_ROLE_KEY", ""))
    return {
        "status": "healthy" if insforge_url and has_service_key else "degraded",
        "url_configured": bool(insforge_url),
        "service_key_configured": has_service_key,
        "note": "配置已就绪（轻量探测，未执行实际查询）",
    }


def _check_ai_gateway() -> dict[str, Any]:
    """检查 AI 网关状态"""
    has_gateway_key = bool(os.getenv("DEERFLOW_GATEWAY_API_KEY", ""))
    byok_store = os.getenv("BYOK_STATS_STORE", "file")
    return {
        "status": "healthy" if has_gateway_key else "degraded",
        "gateway_key_configured": has_gateway_key,
        "byok_stats_store": byok_store,
        # embedding 曾列于此但 gateway 从未提供 embedding 端点（审计 260829 移除，防误导调用方）
        "supported_modes": ["chat", "image", "video", "audio"],
    }


def _check_system_resources() -> dict[str, Any]:
    """检查系统资源（轻量，不依赖 psutil）"""
    # 进程内存使用（通过 /proc/self/status 或 Windows 方式）
    try:
        import psutil  # type: ignore

        process = psutil.Process()
        mem_info = process.memory_info()
        return {
            "status": "healthy",
            "process_memory_mb": round(mem_info.rss / 1024 / 1024, 2),
            "cpu_percent": process.cpu_percent(interval=0.1),
            "python_version": os.sys.version.split()[0] if hasattr(os, "sys") else "unknown",
        }
    except ImportError:
        return {
            "status": "healthy",
            "note": "psutil 未安装，跳过详细资源检查",
            "python_version": "unknown",
        }


@router.get("/api/health")
async def comprehensive_health() -> dict[str, Any]:
    """综合健康检查端点 — 大厂标准

    返回：
    - 服务基本信息
    - 各子系统健康状态
    - 系统资源使用
    - 关键配置摘要（脱敏）
    """
    uptime = _get_uptime_seconds()
    db_status = _check_insforge_db()
    ai_status = _check_ai_gateway()
    sys_status = _check_system_resources()

    # 计算整体状态
    all_statuses = [db_status["status"], ai_status["status"], sys_status["status"]]
    overall_status = "healthy" if all(s == "healthy" for s in all_statuses) else "degraded"

    return {
        "status": overall_status,
        "service": "deer-flow-gateway",
        "version": "2.1.0",
        "uptime_seconds": round(uptime, 2),
        "uptime_human": f"{int(uptime // 3600)}h {int((uptime % 3600) // 60)}m {int(uptime % 60)}s",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "checks": {
            "database": db_status,
            "ai_gateway": ai_status,
            "system": sys_status,
        },
        "config_summary": {
            "byok_enabled": True,
            "byok_stats_store": os.getenv("BYOK_STATS_STORE", "file"),
            "payment_providers": ["antom", "paypal"],
            "i18n_locales": ["zh", "en"],
            "pwa_enabled": True,
        },
    }


@router.get("/api/health/live")
async def liveness_probe() -> dict[str, str]:
    """存活探针（K8s liveness）— 仅检查进程是否存活"""
    return {"status": "alive"}


@router.get("/api/health/ready")
async def readiness_probe() -> dict[str, Any]:
    """就绪探针（K8s readiness）— 检查是否可接收流量"""
    db_status = _check_insforge_db()
    ai_status = _check_ai_gateway()
    ready = db_status["status"] == "healthy" and ai_status["status"] == "healthy"
    return {
        "ready": ready,
        "checks": {
            "database": db_status["status"],
            "ai_gateway": ai_status["status"],
        },
    }


@router.get("/api/health/metrics")
async def health_metrics() -> dict[str, Any]:
    """关键指标摘要 — 用于监控面板"""
    uptime = _get_uptime_seconds()
    return {
        "uptime_seconds": round(uptime, 2),
        "active_connections": "unknown",  # 需要额外统计
        "total_requests": "unknown",  # 需要中间件统计
        "error_rate": "unknown",  # 需要中间件统计
        "byok_keys_count": "unknown",  # 需要查询 DB
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
