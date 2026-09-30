"""
Prometheus 监控端点 — 大厂标准做法
- GET /metrics  输出 Prometheus 格式的指标

指标列表：
- deerflow_up                    服务是否正常运行（1=正常，0=异常）
- deerflow_uptime_seconds        服务运行时长（秒）
- deerflow_config_items_total    配置项总数
- deerflow_byok_keys_total       BYOK 密钥总数
- deerflow_health_checks_total   健康检查次数
- deerflow_http_requests_total   HTTP 请求总数（待接入中间件）
- deerflow_http_errors_total     HTTP 错误总数（待接入中间件）
- deerflow_memory_usage_bytes    内存使用量（字节）
- deerflow_cpu_usage_percent     CPU 使用率（百分比）
"""

import hmac
import logging
import os
import time

from fastapi import APIRouter, Request, Response

logger = logging.getLogger(__name__)
router = APIRouter(tags=["metrics"])

# 服务启动时间
_START_TIME = time.time()

# 计数器
_health_checks_total = 0
_http_requests_total = 0
_http_errors_total = 0


def _get_process_memory_bytes() -> float:
    """获取进程内存使用量（字节）"""
    try:
        import psutil  # type: ignore

        process = psutil.Process()
        return float(process.memory_info().rss)
    except ImportError:
        return 0.0


def _get_cpu_percent() -> float:
    """获取 CPU 使用率（百分比）"""
    try:
        import psutil  # type: ignore

        process = psutil.Process()
        return float(process.cpu_percent(interval=0.1))
    except ImportError:
        return 0.0


def _get_config_items_count() -> int:
    """获取配置项数量（从配置中心缓存）"""
    try:
        from app.gateway.routers.config import _cache_loaded, _config_cache

        if _cache_loaded:
            return len(_config_cache)
    except Exception:
        pass
    return 0


def _format_prometheus_metric(
    name: str,
    value: float | int,
    help_text: str,
    metric_type: str = "gauge",
    labels: dict[str, str] | None = None,
) -> str:
    """格式化 Prometheus 指标"""
    lines = [
        f"# HELP {name} {help_text}",
        f"# TYPE {name} {metric_type}",
    ]

    if labels:
        label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
        lines.append(f"{name}{{{label_str}}} {value}")
    else:
        lines.append(f"{name} {value}")

    return "\n".join(lines)


@router.get("/metrics")
async def prometheus_metrics(request: Request) -> Response:
    """Prometheus 监控指标端点

    认证策略（fail-closed）：
    - 未设置 METRICS_TOKEN 时端点拒绝访问（防止指标泄露到公网）
    - 设置后要求 `Authorization: Bearer <token>` 或 `?token=<token>` 匹配
    """
    expected_token = os.environ.get("METRICS_TOKEN", "")
    if not expected_token:
        return Response(
            content="metrics disabled: set METRICS_TOKEN to expose this endpoint\n",
            status_code=403,
            media_type="text/plain; charset=utf-8",
        )

    auth_header = request.headers.get("authorization", "")
    supplied = auth_header.removeprefix("Bearer ").strip() or request.query_params.get("token", "")
    if not hmac.compare_digest(supplied, expected_token):
        return Response(
            content="unauthorized\n",
            status_code=401,
            media_type="text/plain; charset=utf-8",
        )

    global _health_checks_total
    _health_checks_total += 1

    uptime = time.time() - _START_TIME
    memory_bytes = _get_process_memory_bytes()
    cpu_percent = _get_cpu_percent()
    config_count = _get_config_items_count()

    # 构建 Prometheus 格式输出
    metrics = [
        _format_prometheus_metric(
            "deerflow_up",
            1,
            "Service is up and running (1=up, 0=down)",
        ),
        _format_prometheus_metric(
            "deerflow_uptime_seconds",
            uptime,
            "Service uptime in seconds",
        ),
        _format_prometheus_metric(
            "deerflow_config_items_total",
            config_count,
            "Total number of configuration items",
        ),
        _format_prometheus_metric(
            "deerflow_health_checks_total",
            _health_checks_total,
            "Total number of health check requests",
            "counter",
        ),
        _format_prometheus_metric(
            "deerflow_http_requests_total",
            _http_requests_total,
            "Total number of HTTP requests (requires middleware integration)",
            "counter",
        ),
        _format_prometheus_metric(
            "deerflow_http_errors_total",
            _http_errors_total,
            "Total number of HTTP errors (requires middleware integration)",
            "counter",
        ),
        _format_prometheus_metric(
            "deerflow_memory_usage_bytes",
            memory_bytes,
            "Process memory usage in bytes",
        ),
        _format_prometheus_metric(
            "deerflow_cpu_usage_percent",
            cpu_percent,
            "Process CPU usage percentage",
        ),
        _format_prometheus_metric(
            "deerflow_byok_enabled",
            1 if os.getenv("BYOK_STATS_STORE") else 0,
            "BYOK feature is enabled (1=enabled, 0=disabled)",
        ),
        _format_prometheus_metric(
            "deerflow_byok_stats_store",
            1,
            "BYOK stats storage backend",
            labels={"backend": os.getenv("BYOK_STATS_STORE", "file")},
        ),
    ]

    # 添加空行分隔
    output = "\n\n".join(metrics) + "\n"

    return Response(
        content=output,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


def increment_http_requests() -> None:
    """递增 HTTP 请求计数器（供中间件调用）"""
    global _http_requests_total
    _http_requests_total += 1


def increment_http_errors() -> None:
    """递增 HTTP 错误计数器（供中间件调用）"""
    global _http_errors_total
    _http_errors_total += 1
