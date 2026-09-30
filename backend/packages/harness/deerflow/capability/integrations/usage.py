"""
使用统计集成模块（Usage Integration）
=====================================

负责在运行时自动记录能力使用情况，集成到统一能力使用统计器。

功能：
1. 自动记录Agent调用
2. 自动记录工具调用
3. 自动记录Skill激活
4. 提供装饰器和中间件接口
5. 支持异步记录
"""

import logging
import time
from collections.abc import Callable
from functools import wraps
from threading import Lock
from typing import Any

from deerflow.capability.integrations.coordinator import (
    IntegrationResult,
    IntegrationStatus,
)
from deerflow.capability.registry import CapabilityType
from deerflow.capability.usage import (
    CapabilityUsage,
    CapabilityUsageTracker,
    get_global_usage_tracker,
)

logger = logging.getLogger(__name__)


class UsageIntegration:
    """
    使用统计集成器

    负责在运行时自动记录能力使用情况，集成到统一能力使用统计器。
    """

    def __init__(self, usage_tracker: CapabilityUsageTracker | None = None):
        self.usage_tracker = usage_tracker or get_global_usage_tracker()
        self._enabled = False
        self._lock = Lock()
        self._recorded_count = 0

    def enable(self) -> IntegrationResult:
        """
        启用使用统计跟踪

        Returns:
            集成结果
        """
        result = IntegrationResult(
            integration_name="usage",
            status=IntegrationStatus.SYNCING,
        )

        try:
            with self._lock:
                self._enabled = True

            result.status = IntegrationStatus.COMPLETED
            result.completed_at = time.time()

            logger.info("Usage tracking enabled")

        except Exception as e:
            result.status = IntegrationStatus.FAILED
            result.error_message = str(e)
            result.completed_at = time.time()
            logger.error("Failed to enable usage tracking: %s", e, exc_info=True)

        return result

    def disable(self):
        """禁用使用统计跟踪"""
        with self._lock:
            self._enabled = False
        logger.info("Usage tracking disabled")

    def record_agent_usage(self, agent_name: str, success: bool, latency_ms: float, cost: float = 0.0, domain: str | None = None, user_id: str | None = None, error_type: str | None = None, metadata: dict[str, Any] | None = None):
        """
        记录Agent使用情况

        Args:
            agent_name: Agent名称
            success: 是否成功
            latency_ms: 延迟（毫秒）
            cost: 成本
            domain: 业务域
            user_id: 用户ID
            error_type: 错误类型
            metadata: 元数据
        """
        if not self._enabled:
            return

        try:
            usage = CapabilityUsage(
                capability_name=agent_name,
                capability_type=CapabilityType.AGENT,
                timestamp=time.time(),
                success=success,
                latency_ms=latency_ms,
                cost=cost,
                error_type=error_type,
                domain=domain,
                user_id=user_id,
                metadata=metadata or {},
            )
            self.usage_tracker.record_usage(usage)

            with self._lock:
                self._recorded_count += 1

        except Exception as e:
            logger.debug("Failed to record agent usage: %s", e)

    def record_tool_usage(self, tool_name: str, success: bool, latency_ms: float, cost: float = 0.0, domain: str | None = None, user_id: str | None = None, error_type: str | None = None, metadata: dict[str, Any] | None = None):
        """
        记录工具使用情况

        Args:
            tool_name: 工具名称
            success: 是否成功
            latency_ms: 延迟（毫秒）
            cost: 成本
            domain: 业务域
            user_id: 用户ID
            error_type: 错误类型
            metadata: 元数据
        """
        if not self._enabled:
            return

        try:
            usage = CapabilityUsage(
                capability_name=tool_name,
                capability_type=CapabilityType.TOOL,
                timestamp=time.time(),
                success=success,
                latency_ms=latency_ms,
                cost=cost,
                error_type=error_type,
                domain=domain,
                user_id=user_id,
                metadata=metadata or {},
            )
            self.usage_tracker.record_usage(usage)

            with self._lock:
                self._recorded_count += 1

        except Exception as e:
            logger.debug("Failed to record tool usage: %s", e)

    def record_skill_usage(self, skill_name: str, success: bool, latency_ms: float, cost: float = 0.0, domain: str | None = None, user_id: str | None = None, error_type: str | None = None, metadata: dict[str, Any] | None = None):
        """
        记录Skill使用情况

        Args:
            skill_name: Skill名称
            success: 是否成功
            latency_ms: 延迟（毫秒）
            cost: 成本
            domain: 业务域
            user_id: 用户ID
            error_type: 错误类型
            metadata: 元数据
        """
        if not self._enabled:
            return

        try:
            usage = CapabilityUsage(
                capability_name=skill_name,
                capability_type=CapabilityType.SKILL,
                timestamp=time.time(),
                success=success,
                latency_ms=latency_ms,
                cost=cost,
                error_type=error_type,
                domain=domain,
                user_id=user_id,
                metadata=metadata or {},
            )
            self.usage_tracker.record_usage(usage)

            with self._lock:
                self._recorded_count += 1

        except Exception as e:
            logger.debug("Failed to record skill usage: %s", e)

    def track_agent(self, agent_name: str, domain: str | None = None):
        """
        Agent调用装饰器

        使用方式：
        ```python
        @usage_integration.track_agent("my-agent", domain="content_creation")
        def my_agent_function(*args, **kwargs):
            # Agent逻辑
            return result
        ```
        """

        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()
                success = True
                error_type = None

                try:
                    result = func(*args, **kwargs)
                    return result
                except Exception as e:
                    success = False
                    error_type = type(e).__name__
                    raise
                finally:
                    latency_ms = (time.time() - start_time) * 1000
                    self.record_agent_usage(
                        agent_name=agent_name,
                        success=success,
                        latency_ms=latency_ms,
                        domain=domain,
                        error_type=error_type,
                    )

            return wrapper

        return decorator

    def track_tool(self, tool_name: str, domain: str | None = None):
        """
        工具调用装饰器
        """

        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()
                success = True
                error_type = None

                try:
                    result = func(*args, **kwargs)
                    return result
                except Exception as e:
                    success = False
                    error_type = type(e).__name__
                    raise
                finally:
                    latency_ms = (time.time() - start_time) * 1000
                    self.record_tool_usage(
                        tool_name=tool_name,
                        success=success,
                        latency_ms=latency_ms,
                        domain=domain,
                        error_type=error_type,
                    )

            return wrapper

        return decorator

    @property
    def enabled(self) -> bool:
        """是否已启用"""
        return self._enabled

    @property
    def recorded_count(self) -> int:
        """已记录的使用次数"""
        return self._recorded_count


# 全局使用统计集成器单例
_global_usage_integration: UsageIntegration | None = None
_global_usage_integration_lock = Lock()


def get_global_usage_integration() -> UsageIntegration:
    """获取全局使用统计集成器单例"""
    global _global_usage_integration
    if _global_usage_integration is None:
        with _global_usage_integration_lock:
            if _global_usage_integration is None:
                _global_usage_integration = UsageIntegration()
    return _global_usage_integration
