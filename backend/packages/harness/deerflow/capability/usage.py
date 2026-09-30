"""
能力使用统计器（Capability Usage Tracker）
===========================================

负责统计能力的使用情况，包括调用次数、成功率、延迟、成本等。

核心功能：
1. 调用记录与统计
2. 成功率统计
3. 延迟统计
4. 成本统计
5. 热门能力排行
6. 能力使用趋势分析
"""

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from deerflow.capability.registry import CapabilityType

logger = logging.getLogger(__name__)


@dataclass
class UsageMetrics:
    """使用指标"""

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_latency_ms: float = 0.0
    total_cost: float = 0.0

    # 时间窗口统计
    calls_by_hour: dict[int, int] = field(default_factory=lambda: defaultdict(int))
    calls_by_day: dict[int, int] = field(default_factory=lambda: defaultdict(int))

    # 错误统计
    errors_by_type: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_calls == 0:
            return 0.0
        return self.successful_calls / self.total_calls

    @property
    def avg_latency_ms(self) -> float:
        """平均延迟"""
        if self.total_calls == 0:
            return 0.0
        return self.total_latency_ms / self.total_calls

    @property
    def avg_cost_per_call(self) -> float:
        """平均每次调用成本"""
        if self.total_calls == 0:
            return 0.0
        return self.total_cost / self.total_calls

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "success_rate": self.success_rate,
            "avg_latency_ms": self.avg_latency_ms,
            "total_cost": self.total_cost,
            "avg_cost_per_call": self.avg_cost_per_call,
        }


@dataclass
class CapabilityUsage:
    """能力使用记录"""

    capability_name: str
    capability_type: CapabilityType
    timestamp: float
    success: bool
    latency_ms: float
    cost: float = 0.0
    error_type: str | None = None
    domain: str | None = None
    user_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class CapabilityUsageTracker:
    """
    能力使用统计器

    负责统计能力的使用情况，包括调用次数、成功率、延迟、成本等。
    线程安全，支持并发记录。
    """

    def __init__(self, retention_days: int = 30):
        self._metrics: dict[str, UsageMetrics] = {}
        self._usage_history: list[CapabilityUsage] = []
        self._lock = Lock()
        self._retention_days = retention_days
        self._max_history_size = 100000  # 最大历史记录数

    def record_usage(self, usage: CapabilityUsage):
        """
        记录能力使用情况

        Args:
            usage: 使用记录
        """
        with self._lock:
            key = self._make_key(usage.capability_name, usage.capability_type)

            # 获取或创建指标
            if key not in self._metrics:
                self._metrics[key] = UsageMetrics()

            metrics = self._metrics[key]

            # 更新指标
            metrics.total_calls += 1
            if usage.success:
                metrics.successful_calls += 1
            else:
                metrics.failed_calls += 1
                if usage.error_type:
                    metrics.errors_by_type[usage.error_type] += 1

            metrics.total_latency_ms += usage.latency_ms
            metrics.total_cost += usage.cost

            # 时间窗口统计
            hour = int(usage.timestamp // 3600)
            day = int(usage.timestamp // 86400)
            metrics.calls_by_hour[hour] += 1
            metrics.calls_by_day[day] += 1

            # 添加到历史记录
            self._usage_history.append(usage)

            # 清理过期历史记录
            self._cleanup_old_records()

            logger.debug("Usage recorded: %s (success=%s, latency=%.2fms)", usage.capability_name, usage.success, usage.latency_ms)

    def get_metrics(self, capability_name: str, capability_type: CapabilityType) -> UsageMetrics | None:
        """获取能力使用指标"""
        key = self._make_key(capability_name, capability_type)
        return self._metrics.get(key)

    def get_top_capabilities(self, type: CapabilityType | None = None, limit: int = 10, sort_by: str = "total_calls") -> list[tuple[str, UsageMetrics]]:
        """
        获取热门能力排行

        Args:
            type: 能力类型过滤（可选）
            limit: 返回数量
            sort_by: 排序字段（total_calls, success_rate, avg_latency_ms, total_cost）

        Returns:
            (能力键, 指标) 列表
        """
        with self._lock:
            items = list(self._metrics.items())

            # 按类型过滤
            if type:
                type_prefix = f"{type.value}{self._KEY_SEP}"
                items = [(k, v) for k, v in items if k.startswith(type_prefix)]

            # 排序
            if sort_by == "total_calls":
                items.sort(key=lambda x: x[1].total_calls, reverse=True)
            elif sort_by == "success_rate":
                items.sort(key=lambda x: x[1].success_rate, reverse=True)
            elif sort_by == "avg_latency_ms":
                items.sort(key=lambda x: x[1].avg_latency_ms)
            elif sort_by == "total_cost":
                items.sort(key=lambda x: x[1].total_cost, reverse=True)

            return items[:limit]

    def get_domain_metrics(self, domain: str) -> dict[str, UsageMetrics]:
        """获取业务域的使用指标（聚合）"""
        # 简化实现：实际应该按domain聚合
        # 这里返回所有指标，实际使用时应该过滤
        with self._lock:
            return dict(self._metrics)

    def get_usage_trend(self, capability_name: str, capability_type: CapabilityType, days: int = 7) -> list[dict[str, Any]]:
        """
        获取使用趋势

        Args:
            capability_name: 能力名称
            capability_type: 能力类型
            days: 天数

        Returns:
            每日使用统计列表
        """
        key = self._make_key(capability_name, capability_type)
        metrics = self._metrics.get(key)

        if not metrics:
            return []

        now = time.time()
        trend = []

        for day_offset in range(days - 1, -1, -1):
            day_timestamp = int((now - day_offset * 86400) // 86400)
            calls = metrics.calls_by_day.get(day_timestamp, 0)
            trend.append(
                {
                    "day": day_timestamp,
                    "date": time.strftime("%Y-%m-%d", time.localtime(day_timestamp * 86400)),
                    "calls": calls,
                }
            )

        return trend

    def get_statistics_summary(self) -> dict[str, Any]:
        """获取统计摘要"""
        with self._lock:
            total_capabilities = len(self._metrics)
            total_calls = sum(m.total_calls for m in self._metrics.values())
            total_cost = sum(m.total_cost for m in self._metrics.values())
            avg_success_rate = sum(m.success_rate for m in self._metrics.values()) / total_capabilities if total_capabilities > 0 else 0.0

            return {
                "total_capabilities_tracked": total_capabilities,
                "total_calls": total_calls,
                "total_cost": total_cost,
                "avg_success_rate": avg_success_rate,
                "total_history_records": len(self._usage_history),
            }

    def reset_metrics(self, capability_name: str | None = None, capability_type: CapabilityType | None = None):
        """重置指标"""
        with self._lock:
            if capability_name and capability_type:
                key = self._make_key(capability_name, capability_type)
                if key in self._metrics:
                    self._metrics[key] = UsageMetrics()
            else:
                self._metrics.clear()
                self._usage_history.clear()

    def _cleanup_old_records(self):
        """清理过期记录（调用时需持有锁）

        使用惰性清理策略：只在超过最大数量的 1.5 倍时才触发全量清理，
        避免每次 record_usage 都做 O(n) 遍历。
        """
        # 只在超过软限制时才清理
        soft_limit = int(self._max_history_size * 1.5)
        if len(self._usage_history) <= soft_limit:
            return

        now = time.time()
        cutoff = now - self._retention_days * 86400

        # 先清理过期记录
        active = [r for r in self._usage_history if r.timestamp >= cutoff]

        # 如果仍然超过最大数量，只保留最新记录
        if len(active) > self._max_history_size:
            self._usage_history = active[-self._max_history_size :]
        else:
            self._usage_history = active

    _KEY_SEP = "\x1e"  # 与 registry.py 一致，避免名称碰撞

    def _make_key(self, name: str, type: CapabilityType) -> str:
        return f"{type.value}{self._KEY_SEP}{name}"


# 全局使用统计器单例
_global_usage_tracker: CapabilityUsageTracker | None = None
_global_usage_tracker_lock = Lock()


def get_global_usage_tracker() -> CapabilityUsageTracker:
    """获取全局使用统计器单例"""
    global _global_usage_tracker
    if _global_usage_tracker is None:
        with _global_usage_tracker_lock:
            if _global_usage_tracker is None:
                _global_usage_tracker = CapabilityUsageTracker()
    return _global_usage_tracker
