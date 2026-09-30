"""
能力平台集成协调器（Capability Platform Integration Coordinator）
=================================================================

负责协调各个子系统的集成，包括：
1. 子Agent集成（SubagentIntegration）
2. 工具集成（ToolIntegration）
3. Skill集成（SkillIntegration）
4. 使用统计集成（UsageIntegration）

提供统一的初始化、同步、状态查询接口。
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Any

from deerflow.capability.registry import (
    CapabilityRegistry,
    get_global_registry,
)
from deerflow.capability.usage import (
    CapabilityUsageTracker,
    get_global_usage_tracker,
)

logger = logging.getLogger(__name__)


class IntegrationStatus(Enum):
    """集成状态枚举"""

    NOT_STARTED = "not_started"
    INITIALIZING = "initializing"
    SYNCING = "syncing"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


@dataclass
class IntegrationResult:
    """集成结果"""

    integration_name: str
    status: IntegrationStatus
    registered_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    error_message: str | None = None
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None

    @property
    def duration_ms(self) -> float:
        """耗时（毫秒）"""
        end = self.completed_at or time.time()
        return (end - self.started_at) * 1000

    def to_dict(self) -> dict[str, Any]:
        return {
            "integration_name": self.integration_name,
            "status": self.status.value,
            "registered_count": self.registered_count,
            "failed_count": self.failed_count,
            "skipped_count": self.skipped_count,
            "error_message": self.error_message,
            "duration_ms": self.duration_ms,
        }


class CapabilityPlatformIntegration:
    """
    能力平台集成协调器

    负责协调各个子系统的集成，提供统一的初始化、同步、状态查询接口。

    使用方式：
    ```python
    # 初始化集成
    integration = CapabilityPlatformIntegration()
    results = integration.initialize_all()

    # 查看集成状态
    status = integration.get_integration_status()

    # 重新同步某个子系统
    integration.sync_subagents()
    ```
    """

    def __init__(self, registry: CapabilityRegistry | None = None, usage_tracker: CapabilityUsageTracker | None = None):
        self.registry = registry or get_global_registry()
        self.usage_tracker = usage_tracker or get_global_usage_tracker()

        self._lock = Lock()
        self._integration_results: dict[str, IntegrationResult] = {}
        self._initialized = False

        # 子系统集成器（延迟初始化）
        self._subagent_integration = None
        self._tool_integration = None
        self._skill_integration = None
        self._usage_integration = None

    def initialize_all(self, enable_subagent: bool = True, enable_tool: bool = True, enable_skill: bool = True, enable_usage: bool = True) -> list[IntegrationResult]:
        """
        初始化所有子系统集成

        Args:
            enable_subagent: 是否启用子Agent集成
            enable_tool: 是否启用工具集成
            enable_skill: 是否启用Skill集成
            enable_usage: 是否启用使用统计集成

        Returns:
            集成结果列表
        """
        with self._lock:
            if self._initialized:
                logger.warning("Integration already initialized, skipping")
                return list(self._integration_results.values())

            logger.info("Starting capability platform integration...")
            results = []

            # 1. 子Agent集成
            if enable_subagent:
                try:
                    result = self.sync_subagents()
                    results.append(result)
                except Exception as e:
                    logger.error("Subagent integration failed: %s", e, exc_info=True)
                    results.append(
                        IntegrationResult(
                            integration_name="subagent",
                            status=IntegrationStatus.FAILED,
                            error_message=str(e),
                        )
                    )

            # 2. 工具集成
            if enable_tool:
                try:
                    result = self.sync_tools()
                    results.append(result)
                except Exception as e:
                    logger.error("Tool integration failed: %s", e, exc_info=True)
                    results.append(
                        IntegrationResult(
                            integration_name="tool",
                            status=IntegrationStatus.FAILED,
                            error_message=str(e),
                        )
                    )

            # 3. Skill集成
            if enable_skill:
                try:
                    result = self.sync_skills()
                    results.append(result)
                except Exception as e:
                    logger.error("Skill integration failed: %s", e, exc_info=True)
                    results.append(
                        IntegrationResult(
                            integration_name="skill",
                            status=IntegrationStatus.FAILED,
                            error_message=str(e),
                        )
                    )

            # 4. 使用统计集成
            if enable_usage:
                try:
                    result = self.enable_usage_tracking()
                    results.append(result)
                except Exception as e:
                    logger.error("Usage integration failed: %s", e, exc_info=True)
                    results.append(
                        IntegrationResult(
                            integration_name="usage",
                            status=IntegrationStatus.FAILED,
                            error_message=str(e),
                        )
                    )

            self._initialized = True

            # 统计总体结果
            total_registered = sum(r.registered_count for r in results)
            total_failed = sum(r.failed_count for r in results)

            logger.info("Capability platform integration completed: %d registered, %d failed, %d integrations", total_registered, total_failed, len(results))

            return results

    def sync_subagents(self) -> IntegrationResult:
        """同步子Agent"""
        from deerflow.capability.integrations.subagent import SubagentIntegration

        if self._subagent_integration is None:
            self._subagent_integration = SubagentIntegration(self.registry)

        result = self._subagent_integration.sync()
        self._integration_results["subagent"] = result
        return result

    def sync_tools(self) -> IntegrationResult:
        """同步工具"""
        from deerflow.capability.integrations.tool import ToolIntegration

        if self._tool_integration is None:
            self._tool_integration = ToolIntegration(self.registry)

        result = self._tool_integration.sync()
        self._integration_results["tool"] = result
        return result

    def sync_skills(self) -> IntegrationResult:
        """同步Skill"""
        from deerflow.capability.integrations.skill import SkillIntegration

        if self._skill_integration is None:
            self._skill_integration = SkillIntegration(self.registry)

        result = self._skill_integration.sync()
        self._integration_results["skill"] = result
        return result

    def enable_usage_tracking(self) -> IntegrationResult:
        """启用使用统计跟踪"""
        from deerflow.capability.integrations.usage import UsageIntegration

        if self._usage_integration is None:
            self._usage_integration = UsageIntegration(self.usage_tracker)

        result = self._usage_integration.enable()
        self._integration_results["usage"] = result
        return result

    def get_integration_status(self) -> dict[str, Any]:
        """获取集成状态"""
        with self._lock:
            results = [r.to_dict() for r in self._integration_results.values()]

            total_registered = sum(r.registered_count for r in self._integration_results.values())
            total_failed = sum(r.failed_count for r in self._integration_results.values())

            # 计算总体状态
            if not self._integration_results:
                overall_status = IntegrationStatus.NOT_STARTED
            elif all(r.status == IntegrationStatus.COMPLETED for r in self._integration_results.values()):
                overall_status = IntegrationStatus.COMPLETED
            elif any(r.status == IntegrationStatus.FAILED for r in self._integration_results.values()):
                overall_status = IntegrationStatus.PARTIAL
            else:
                overall_status = IntegrationStatus.SYNCING

            return {
                "initialized": self._initialized,
                "overall_status": overall_status.value,
                "total_registered": total_registered,
                "total_failed": total_failed,
                "integrations": results,
                "registry_statistics": self.registry.get_statistics(),
            }

    def reset(self):
        """重置集成状态"""
        with self._lock:
            self._integration_results.clear()
            self._initialized = False
            self._subagent_integration = None
            self._tool_integration = None
            self._skill_integration = None
            self._usage_integration = None
            logger.info("Integration state reset")


# 全局集成协调器单例
_global_integration: CapabilityPlatformIntegration | None = None
_global_integration_lock = Lock()


def get_global_integration() -> CapabilityPlatformIntegration:
    """获取全局集成协调器单例"""
    global _global_integration
    if _global_integration is None:
        with _global_integration_lock:
            if _global_integration is None:
                _global_integration = CapabilityPlatformIntegration()
    return _global_integration


def initialize_capability_platform(
    enable_subagent: bool = True,
    enable_tool: bool = True,
    enable_skill: bool = True,
    enable_usage: bool = True,
) -> list[IntegrationResult]:
    """
    初始化能力平台（便捷函数）

    在系统启动时调用，自动集成所有子系统的能力。

    Args:
        enable_subagent: 是否启用子Agent集成
        enable_tool: 是否启用工具集成
        enable_skill: 是否启用Skill集成
        enable_usage: 是否启用使用统计集成

    Returns:
        集成结果列表
    """
    integration = get_global_integration()
    return integration.initialize_all(
        enable_subagent=enable_subagent,
        enable_tool=enable_tool,
        enable_skill=enable_skill,
        enable_usage=enable_usage,
    )
