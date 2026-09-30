"""
能力平台启动初始化器（Capability Platform Bootstrap）
=====================================================

负责在系统启动时自动初始化能力平台，包括：
1. 初始化统一能力注册中心
2. 集成现有子Agent、工具、Skill
3. 启用使用统计跟踪
4. 提供启动状态查询

使用方式：
```python
# 在系统启动时调用
from deerflow.capability.bootstrap import initialize_capability_platform_on_startup

initialize_capability_platform_on_startup()

# 或者使用便捷函数
from deerflow.capability import bootstrap
bootstrap.start()
```
"""

import logging
import time
from typing import Any

from deerflow.capability.integrations.coordinator import (
    CapabilityPlatformIntegration,
    IntegrationResult,
    get_global_integration,
)
from deerflow.capability.registry import (
    CapabilityRegistry,
    get_global_registry,
)
from deerflow.capability.usage import (
    CapabilityUsageTracker,
    get_global_usage_tracker,
)

logger = logging.getLogger(__name__)


class CapabilityPlatformBootstrap:
    """
    能力平台启动初始化器

    负责在系统启动时自动初始化能力平台。
    """

    def __init__(self, registry: CapabilityRegistry | None = None, usage_tracker: CapabilityUsageTracker | None = None, integration: CapabilityPlatformIntegration | None = None):
        self.registry = registry or get_global_registry()
        self.usage_tracker = usage_tracker or get_global_usage_tracker()
        self.integration = integration or get_global_integration()

        self._started = False
        self._start_time: float | None = None
        self._results: list[IntegrationResult] = []

    def start(self, enable_subagent: bool = True, enable_tool: bool = True, enable_skill: bool = True, enable_usage: bool = True, register_builtin_capabilities: bool = True) -> dict[str, Any]:
        """
        启动能力平台

        Args:
            enable_subagent: 是否启用子Agent集成
            enable_tool: 是否启用工具集成
            enable_skill: 是否启用Skill集成
            enable_usage: 是否启用使用统计集成
            register_builtin_capabilities: 是否注册内置能力示例

        Returns:
            启动结果
        """
        if self._started:
            logger.warning("Capability platform already started")
            return self.get_status()

        logger.info("=" * 60)
        logger.info("Starting Capability Platform...")
        logger.info("=" * 60)

        start_time = time.time()

        try:
            # 1. 注册内置能力示例（可选）
            if register_builtin_capabilities:
                self._register_builtin_capabilities()

            # 2. 初始化所有子系统集成
            self._results = self.integration.initialize_all(
                enable_subagent=enable_subagent,
                enable_tool=enable_tool,
                enable_skill=enable_skill,
                enable_usage=enable_usage,
            )

            self._started = True
            self._start_time = time.time()

            # 统计结果
            total_registered = sum(r.registered_count for r in self._results)
            total_failed = sum(r.failed_count for r in self._results)
            total_duration = (time.time() - start_time) * 1000

            logger.info("=" * 60)
            logger.info("Capability Platform started successfully: %d registered, %d failed, %.0fms", total_registered, total_failed, total_duration)
            logger.info("=" * 60)

            return {
                "success": True,
                "started": True,
                "total_registered": total_registered,
                "total_failed": total_failed,
                "duration_ms": total_duration,
                "integrations": [r.to_dict() for r in self._results],
                "registry_statistics": self.registry.get_statistics(),
            }

        except Exception as e:
            logger.error("Failed to start capability platform: %s", e, exc_info=True)
            return {
                "success": False,
                "started": False,
                "error": str(e),
                "integrations": [r.to_dict() for r in self._results],
            }

    def stop(self) -> dict[str, Any]:
        """
        停止能力平台

        Returns:
            停止结果
        """
        if not self._started:
            return {"success": True, "stopped": False, "message": "Not started"}

        logger.info("Stopping Capability Platform...")

        # 重置集成状态
        self.integration.reset()

        self._started = False
        self._start_time = None
        self._results = []

        logger.info("Capability Platform stopped")
        return {"success": True, "stopped": True}

    def get_status(self) -> dict[str, Any]:
        """
        获取能力平台状态

        Returns:
            状态信息
        """
        return {
            "started": self._started,
            "start_time": self._start_time,
            "uptime_seconds": (time.time() - self._start_time) if self._start_time else 0,
            "integration_status": self.integration.get_integration_status(),
            "registry_statistics": self.registry.get_statistics(),
            "usage_statistics": self.usage_tracker.get_statistics_summary(),
        }

    def _register_builtin_capabilities(self):
        """注册内置能力示例"""
        try:
            from deerflow.capability.integration import register_builtin_capabilities

            count = register_builtin_capabilities(self.registry)
            logger.info("Registered %d builtin capabilities", count)
        except ImportError:
            logger.debug("Builtin capabilities registration not available")
        except Exception as e:
            logger.debug("Failed to register builtin capabilities: %s", e)


# 全局启动初始化器单例
_global_bootstrap: CapabilityPlatformBootstrap | None = None
_global_bootstrap_lock = None  # 延迟导入Lock


def get_global_bootstrap() -> CapabilityPlatformBootstrap:
    """获取全局启动初始化器单例"""
    global _global_bootstrap, _global_bootstrap_lock
    if _global_bootstrap_lock is None:
        from threading import Lock

        _global_bootstrap_lock = Lock()

    if _global_bootstrap is None:
        with _global_bootstrap_lock:
            if _global_bootstrap is None:
                _global_bootstrap = CapabilityPlatformBootstrap()
    return _global_bootstrap


def initialize_capability_platform_on_startup(
    enable_subagent: bool = True,
    enable_tool: bool = True,
    enable_skill: bool = True,
    enable_usage: bool = True,
) -> dict[str, Any]:
    """
    系统启动时初始化能力平台（便捷函数）

    在应用启动时调用，自动完成能力平台的所有初始化工作。

    Args:
        enable_subagent: 是否启用子Agent集成
        enable_tool: 是否启用工具集成
        enable_skill: 是否启用Skill集成
        enable_usage: 是否启用使用统计集成

    Returns:
        初始化结果
    """
    bootstrap = get_global_bootstrap()
    return bootstrap.start(
        enable_subagent=enable_subagent,
        enable_tool=enable_tool,
        enable_skill=enable_skill,
        enable_usage=enable_usage,
    )


# 便捷别名
start = initialize_capability_platform_on_startup


def get_capability_platform_status() -> dict[str, Any]:
    """获取能力平台状态（便捷函数）"""
    bootstrap = get_global_bootstrap()
    return bootstrap.get_status()
