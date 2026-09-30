"""
Gateway Prometheus Metrics 模块

提供 HTTP 请求指标、数据库连接指标、AI 模型调用指标等。
参考海内外大厂可观测性最佳实践：
- RED 方法（Rate/Errors/Duration）
- USE 方法（Utilization/Saturation/Errors）
- 四大黄金信号（延迟/流量/错误/饱和度）
"""

import logging
import time

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

logger = logging.getLogger(__name__)

# ============================================================
# HTTP 请求指标（RED 方法）
# ============================================================

http_requests_total = Counter(
    "http_requests_total",
    "HTTP 请求总数",
    ["method", "endpoint", "status", "agent_type"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP 请求延迟（秒）",
    ["method", "endpoint", "agent_type"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
)

http_requests_in_progress = Gauge(
    "http_requests_in_progress",
    "正在处理的 HTTP 请求数",
    ["method", "endpoint"],
)

http_errors_total = Counter(
    "http_errors_total",
    "HTTP 错误总数（5xx）",
    ["method", "endpoint", "error_type"],
)

# ============================================================
# 数据库指标（USE 方法）
# ============================================================

database_connections_active = Gauge(
    "database_connections_active",
    "活跃数据库连接数",
    ["database", "pool"],
)

database_connections_idle = Gauge(
    "database_connections_idle",
    "空闲数据库连接数",
    ["database", "pool"],
)

database_query_duration_seconds = Histogram(
    "database_query_duration_seconds",
    "数据库查询延迟（秒）",
    ["database", "query_type"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)

database_query_errors_total = Counter(
    "database_query_errors_total",
    "数据库查询错误总数",
    ["database", "error_type"],
)

# ============================================================
# AI 模型调用指标
# ============================================================

ai_model_calls_total = Counter(
    "ai_model_calls_total",
    "AI 模型调用总数",
    ["model", "provider", "agent_type", "status"],
)

ai_model_call_duration_seconds = Histogram(
    "ai_model_call_duration_seconds",
    "AI 模型调用延迟（秒）",
    ["model", "provider"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300),
)

ai_model_call_tokens_total = Counter(
    "ai_model_call_tokens_total",
    "AI 模型调用 Token 总数",
    ["model", "provider", "token_type"],  # prompt/completion/total
)

ai_model_call_errors_total = Counter(
    "ai_model_call_errors_total",
    "AI 模型调用错误总数",
    ["model", "provider", "error_type"],
)

ai_model_cost_total = Counter(
    "ai_model_cost_total",
    "AI 模型调用成本（美元）",
    ["model", "provider"],
)

# ============================================================
# 业务指标
# ============================================================

studio_albums_created_total = Counter(
    "studio_albums_created_total",
    "创建的项目总数",
    ["agent_type", "project_type"],
)

studio_albums_completed_total = Counter(
    "studio_albums_completed_total",
    "完成的项目总数",
    ["agent_type", "project_type"],
)

studio_albums_failed_total = Counter(
    "studio_albums_failed_total",
    "失败的项目总数",
    ["agent_type", "project_type", "failure_stage"],
)

studio_album_duration_seconds = Histogram(
    "studio_album_duration_seconds",
    "项目完成时长（秒）",
    ["agent_type", "project_type"],
    buckets=(60, 300, 600, 1800, 3600, 7200, 14400, 28800),
)

# ============================================================
# 管线健康度指标
# ============================================================

studio_pipeline_mismatched_albums_total = Counter(
    "studio_pipeline_mismatched_albums_total",
    "检测到不匹配节点类型的项目总数（旧版管线脏数据）",
    ["album_type", "mismatched_node_type"],
)

studio_pipeline_nodes_skipped_total = Counter(
    "studio_pipeline_nodes_skipped_total",
    "因节点类型不匹配而被跳过执行的节点总数",
    ["album_type", "node_type"],
)

studio_pipeline_health_score = Gauge(
    "studio_pipeline_health_score",
    "管线健康度评分（0-100，匹配节点数/总节点数）",
    ["album_type"],
)

# ============================================================
# 队列指标（Procrastinate）
# ============================================================

queue_jobs_total = Gauge(
    "queue_jobs_total",
    "队列任务总数（按状态）",
    ["queue_name", "status"],
)

queue_job_duration_seconds = Histogram(
    "queue_job_duration_seconds",
    "任务执行时长（秒）",
    ["queue_name", "task_name"],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600),
)

queue_job_wait_duration_seconds = Histogram(
    "queue_job_wait_duration_seconds",
    "任务等待时长（秒）",
    ["queue_name"],
    buckets=(0.1, 0.5, 1, 5, 10, 30, 60, 120, 300, 600),
)

queue_workers_active = Gauge(
    "queue_workers_active",
    "活跃 worker 数",
    ["queue_name"],
)

# ============================================================
# 系统指标
# ============================================================

app_info = Gauge(
    "app_info",
    "应用信息",
    ["version", "environment", "git_commit"],
)

app_start_time_seconds = Gauge(
    "app_start_time_seconds",
    "应用启动时间（Unix 时间戳）",
)

app_uptime_seconds = Gauge(
    "app_uptime_seconds",
    "应用运行时长（秒）",
)


# ============================================================
# 辅助函数
# ============================================================


def record_http_request(
    method: str,
    endpoint: str,
    status: int,
    duration: float,
    agent_type: str = "unknown",
) -> None:
    """记录 HTTP 请求指标"""
    status_str = str(status)
    http_requests_total.labels(
        method=method,
        endpoint=endpoint,
        status=status_str,
        agent_type=agent_type,
    ).inc()
    http_request_duration_seconds.labels(
        method=method,
        endpoint=endpoint,
        agent_type=agent_type,
    ).observe(duration)

    if status >= 500:
        http_errors_total.labels(
            method=method,
            endpoint=endpoint,
            error_type=f"http_{status}",
        ).inc()


def record_ai_model_call(
    model: str,
    provider: str,
    duration: float,
    status: str = "success",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cost: float = 0.0,
    agent_type: str = "unknown",
    error_type: str = "",
) -> None:
    """记录 AI 模型调用指标"""
    ai_model_calls_total.labels(
        model=model,
        provider=provider,
        agent_type=agent_type,
        status=status,
    ).inc()
    ai_model_call_duration_seconds.labels(
        model=model,
        provider=provider,
    ).observe(duration)

    if prompt_tokens > 0:
        ai_model_call_tokens_total.labels(
            model=model,
            provider=provider,
            token_type="prompt",
        ).inc(prompt_tokens)
    if completion_tokens > 0:
        ai_model_call_tokens_total.labels(
            model=model,
            provider=provider,
            token_type="completion",
        ).inc(completion_tokens)
    if prompt_tokens > 0 or completion_tokens > 0:
        ai_model_call_tokens_total.labels(
            model=model,
            provider=provider,
            token_type="total",
        ).inc(prompt_tokens + completion_tokens)

    if cost > 0:
        ai_model_cost_total.labels(
            model=model,
            provider=provider,
        ).inc(cost)

    if status == "error" and error_type:
        ai_model_call_errors_total.labels(
            model=model,
            provider=provider,
            error_type=error_type,
        ).inc()


def get_metrics_response():
    """获取 Prometheus metrics 响应"""
    from fastapi import Response

    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


def init_metrics(version: str = "unknown", environment: str = "production") -> None:
    """初始化 metrics（设置应用信息和启动时间）"""
    app_info.labels(
        version=version,
        environment=environment,
        git_commit="unknown",
    ).set(1)
    app_start_time_seconds.set(time.time())
    logger.info(f"Prometheus metrics initialized (version={version}, env={environment})")
