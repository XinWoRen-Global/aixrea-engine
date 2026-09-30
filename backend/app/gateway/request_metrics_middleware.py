"""
HTTP 请求计数中间件 — 大厂标准做法
- 统计每个 HTTP 请求的总数、错误数、延迟
- 接入 Prometheus metrics 端点
- 支持按路径、方法、状态码分类统计

使用方式：
    from app.gateway.request_metrics_middleware import RequestMetricsMiddleware
    app.add_middleware(RequestMetricsMiddleware)
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

# 全局统计数据（内存级，多进程部署需改用 Redis/DB）
_request_stats: dict[str, Any] = {
    "total_requests": 0,
    "total_errors": 0,
    "total_latency_seconds": 0.0,
    "by_method": defaultdict(int),
    "by_path": defaultdict(int),
    "by_status": defaultdict(int),
    "by_method_path_status": defaultdict(int),
}


class RequestMetricsMiddleware:
    """HTTP 请求计数中间件

    统计：
    - 请求总数（按方法、路径、状态码分类）
    - 错误总数（4xx/5xx）
    - 请求延迟（总延迟、平均延迟）
    - 接入 Prometheus metrics 端点
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 跳过健康检查和 metrics 端点，避免统计噪音
        path = scope.get("path", "")
        if path in ("/health", "/metrics", "/api/health", "/api/health/live", "/api/health/ready"):
            await self.app(scope, receive, send)
            return

        start_time = time.time()
        method = scope.get("method", "UNKNOWN")
        status_code = 0

        async def send_with_metrics(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
            await send(message)

        try:
            await self.app(scope, receive, send_with_metrics)
        except Exception:
            # 记录异常请求
            status_code = 500
            _request_stats["total_errors"] += 1
            _request_stats["by_status"]["500"] += 1
            raise
        finally:
            # 统计请求
            latency = time.time() - start_time
            _request_stats["total_requests"] += 1
            _request_stats["total_latency_seconds"] += latency
            _request_stats["by_method"][method] += 1
            _request_stats["by_path"][path] += 1
            _request_stats["by_status"][str(status_code)] += 1
            _request_stats["by_method_path_status"][f"{method}|{path}|{status_code}"] += 1

            # 错误统计（4xx/5xx）
            if status_code >= 400:
                _request_stats["total_errors"] += 1

            # 接入 Prometheus metrics（如果已导入）
            try:
                from app.gateway.routers.metrics import increment_http_errors, increment_http_requests

                increment_http_requests()
                if status_code >= 400:
                    increment_http_errors()
            except ImportError:
                pass  # metrics 模块未加载时跳过


def get_request_stats() -> dict[str, Any]:
    """获取请求统计数据（用于监控面板）"""
    total = _request_stats["total_requests"]
    avg_latency = _request_stats["total_latency_seconds"] / total if total > 0 else 0.0
    error_rate = (_request_stats["total_errors"] / total * 100) if total > 0 else 0.0

    return {
        "total_requests": total,
        "total_errors": _request_stats["total_errors"],
        "error_rate_percent": round(error_rate, 2),
        "avg_latency_seconds": round(avg_latency, 4),
        "total_latency_seconds": round(_request_stats["total_latency_seconds"], 4),
        "by_method": dict(_request_stats["by_method"]),
        "by_path": dict(sorted(_request_stats["by_path"].items(), key=lambda x: -x[1])[:20]),
        "by_status": dict(_request_stats["by_status"]),
        "top_endpoints": dict(sorted(_request_stats["by_path"].items(), key=lambda x: -x[1])[:10]),
    }


def reset_request_stats() -> None:
    """重置请求统计（用于测试或定期重置）"""
    _request_stats["total_requests"] = 0
    _request_stats["total_errors"] = 0
    _request_stats["total_latency_seconds"] = 0.0
    _request_stats["by_method"].clear()
    _request_stats["by_path"].clear()
    _request_stats["by_status"].clear()
    _request_stats["by_method_path_status"].clear()
    logger.info("Request stats reset")
