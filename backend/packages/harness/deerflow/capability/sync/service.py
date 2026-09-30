"""
能力同步服务（Capability Sync Service）
========================================

负责Deerflow能力注册中心与外部系统的双向同步。

功能：
1. 全量同步：将所有能力从一个系统同步到另一个系统
2. 增量同步：只同步变更的能力
3. 冲突检测和解决
4. 同步状态跟踪
5. 同步日志记录
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from threading import Lock
from typing import Any

from deerflow.capability.registry import (
    CapabilityRegistry,
    get_global_registry,
)
from deerflow.capability.sync.adapter import (
    InsForgeAdapter,
    SyncAdapter,
)
from deerflow.capability.sync.config import SyncConfig, get_sync_config

logger = logging.getLogger(__name__)


class SyncDirection(Enum):
    """同步方向枚举"""

    TO_EXTERNAL = "to_external"  # Deerflow → 外部系统
    FROM_EXTERNAL = "from_external"  # 外部系统 → Deerflow
    BIDIRECTIONAL = "bidirectional"  # 双向同步


class SyncMode(Enum):
    """同步模式枚举"""

    FULL = "full"  # 全量同步
    INCREMENTAL = "incremental"  # 增量同步


@dataclass
class SyncResult:
    """同步结果"""

    direction: SyncDirection
    mode: SyncMode
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None

    # 统计
    total_source: int = 0
    created: int = 0
    updated: int = 0
    deleted: int = 0
    skipped: int = 0
    failed: int = 0

    # 错误信息
    errors: list[str] = field(default_factory=list)

    @property
    def duration_ms(self) -> float:
        """耗时（毫秒）"""
        end = self.completed_at or time.time()
        return (end - self.started_at) * 1000

    @property
    def success(self) -> bool:
        """是否成功"""
        return self.failed == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction.value,
            "mode": self.mode.value,
            "duration_ms": self.duration_ms,
            "total_source": self.total_source,
            "created": self.created,
            "updated": self.updated,
            "deleted": self.deleted,
            "skipped": self.skipped,
            "failed": self.failed,
            "success": self.success,
            "errors": self.errors[:10],  # 只返回前10个错误
        }


class CapabilitySyncService:
    """
    能力同步服务

    负责Deerflow能力注册中心与外部系统的双向同步。
    """

    def __init__(self, registry: CapabilityRegistry | None = None, adapter: SyncAdapter | None = None, config: SyncConfig | None = None):
        self.registry = registry or get_global_registry()
        self.config = config or get_sync_config()

        # 使用配置初始化适配器（如果没有显式传入）
        if adapter is None:
            adapter = InsForgeAdapter(
                database_url=self.config.insforge_database_url,
                api_key=self.config.insforge_api_key,
                base_url=self.config.insforge_base_url,
                table_name=self.config.insforge_table_name,
            )
        self.adapter = adapter

        self._lock = Lock()
        self._syncing = False
        self._last_sync_time: datetime | None = None
        self._sync_history: list[SyncResult] = []

        # 外部ID映射：capability_name -> external_id
        self._external_id_mapping: dict[str, str] = {}

        # 能力名称映射：external_id -> capability_name
        self._capability_name_mapping: dict[str, str] = {}

        # 自动同步线程
        self._auto_sync_thread = None
        self._auto_sync_running = False

    def start_auto_sync(self):
        """启动自动同步（后台线程）"""
        if not self.config.sync_enabled:
            logger.info("Auto sync is disabled by config")
            return

        if self._auto_sync_running:
            logger.warning("Auto sync is already running")
            return

        import threading

        self._auto_sync_running = True
        self._auto_sync_thread = threading.Thread(
            target=self._auto_sync_loop,
            daemon=True,
            name="capability-sync",
        )
        self._auto_sync_thread.start()
        logger.info("Auto sync started (interval=%ds)", self.config.sync_interval_seconds)

    def stop_auto_sync(self):
        """停止自动同步"""
        self._auto_sync_running = False
        if self._auto_sync_thread:
            self._auto_sync_thread.join(timeout=5)
            self._auto_sync_thread = None
        logger.info("Auto sync stopped")

    def _auto_sync_loop(self):
        """自动同步循环"""
        # 启动时先执行一次同步
        if self.config.sync_on_startup:
            try:
                logger.info("Running initial sync on startup")
                self.sync_bidirectional(SyncMode.INCREMENTAL)
            except Exception as e:
                logger.error("Initial sync failed: %s", e, exc_info=True)

        # 定期同步
        while self._auto_sync_running:
            try:
                time.sleep(self.config.sync_interval_seconds)
                if not self._auto_sync_running:
                    break

                logger.debug("Running scheduled auto sync")
                self.sync_bidirectional(SyncMode.INCREMENTAL)
            except Exception as e:
                logger.error("Auto sync iteration failed: %s", e, exc_info=True)
                time.sleep(self.config.retry_delay_seconds)

    def sync_to_external(self, mode: SyncMode = SyncMode.FULL) -> SyncResult:
        """
        同步到外部系统（Deerflow → 外部系统）

        Args:
            mode: 同步模式（全量/增量）

        Returns:
            同步结果
        """
        result = SyncResult(
            direction=SyncDirection.TO_EXTERNAL,
            mode=mode,
        )

        with self._lock:
            if self._syncing:
                result.errors.append("Sync already in progress")
                result.completed_at = time.time()
                return result

            self._syncing = True

        try:
            logger.info("Starting sync to external system (mode=%s)", mode.value)

            # 1. 获取所有能力
            capabilities = self.registry.get_all()
            result.total_source = len(capabilities)

            logger.info("Found %d capabilities in registry", len(capabilities))

            # 2. 逐个同步
            for capability in capabilities:
                try:
                    # 检查是否已同步过
                    external_id = self._external_id_mapping.get(capability.name)

                    if external_id:
                        # 已存在，检查是否需要更新
                        if mode == SyncMode.INCREMENTAL:
                            # 增量同步：检查updated_at
                            # 简化实现：假设都需要更新
                            pass

                        # 更新
                        if self.adapter.update_capability(external_id, capability):
                            result.updated += 1
                        else:
                            result.failed += 1
                            result.errors.append(f"Failed to update {capability.name}")
                    else:
                        # 不存在，创建
                        external_id = self.adapter.create_capability(capability)
                        if external_id:
                            self._external_id_mapping[capability.name] = external_id
                            self._capability_name_mapping[external_id] = capability.name
                            result.created += 1
                        else:
                            result.failed += 1
                            result.errors.append(f"Failed to create {capability.name}")

                except Exception as e:
                    logger.error("Failed to sync capability %s: %s", capability.name, e, exc_info=True)
                    result.failed += 1
                    result.errors.append(f"{capability.name}: {str(e)}")

            result.completed_at = time.time()
            self._last_sync_time = datetime.now()
            self._sync_history.append(result)

            logger.info("Sync to external completed: %d created, %d updated, %d failed", result.created, result.updated, result.failed)

        except Exception as e:
            result.failed += 1
            result.errors.append(str(e))
            result.completed_at = time.time()
            logger.error("Sync to external failed: %s", e, exc_info=True)
        finally:
            with self._lock:
                self._syncing = False

        return result

    def sync_from_external(self, mode: SyncMode = SyncMode.FULL) -> SyncResult:
        """
        从外部系统同步（外部系统 → Deerflow）

        Args:
            mode: 同步模式（全量/增量）

        Returns:
            同步结果
        """
        result = SyncResult(
            direction=SyncDirection.FROM_EXTERNAL,
            mode=mode,
        )

        with self._lock:
            if self._syncing:
                result.errors.append("Sync already in progress")
                result.completed_at = time.time()
                return result

            self._syncing = True

        try:
            logger.info("Starting sync from external system (mode=%s)", mode.value)

            # 1. 获取外部能力
            if mode == SyncMode.INCREMENTAL and self._last_sync_time:
                external_capabilities = self.adapter.get_changed_since(self._last_sync_time)
            else:
                external_capabilities = self.adapter.get_all_capabilities()

            result.total_source = len(external_capabilities)

            logger.info("Found %d capabilities in external system", len(external_capabilities))

            # 2. 逐个同步
            for ext_cap in external_capabilities:
                try:
                    # 转换为CapabilityMetadata
                    capability = ext_cap.to_capability_metadata()

                    # 检查是否已存在
                    existing = self.registry.get(capability.name, capability.type)

                    if existing:
                        # 已存在，跳过（或更新）
                        result.skipped += 1
                    else:
                        # 不存在，注册
                        if self.registry.register(capability):
                            # 记录映射
                            self._external_id_mapping[capability.name] = ext_cap.external_id
                            self._capability_name_mapping[ext_cap.external_id] = capability.name
                            result.created += 1
                        else:
                            result.failed += 1
                            result.errors.append(f"Failed to register {capability.name}")

                except Exception as e:
                    logger.error("Failed to sync external capability %s: %s", ext_cap.name, e, exc_info=True)
                    result.failed += 1
                    result.errors.append(f"{ext_cap.name}: {str(e)}")

            result.completed_at = time.time()
            self._last_sync_time = datetime.now()
            self._sync_history.append(result)

            logger.info("Sync from external completed: %d created, %d skipped, %d failed", result.created, result.skipped, result.failed)

        except Exception as e:
            result.failed += 1
            result.errors.append(str(e))
            result.completed_at = time.time()
            logger.error("Sync from external failed: %s", e, exc_info=True)
        finally:
            with self._lock:
                self._syncing = False

        return result

    def sync_bidirectional(self, mode: SyncMode = SyncMode.FULL) -> tuple[SyncResult, SyncResult]:
        """
        双向同步

        Args:
            mode: 同步模式

        Returns:
            (to_external_result, from_external_result)
        """
        to_result = self.sync_to_external(mode)
        from_result = self.sync_from_external(mode)
        return to_result, from_result

    def get_sync_status(self) -> dict[str, Any]:
        """获取同步状态"""
        return {
            "syncing": self._syncing,
            "auto_sync_running": self._auto_sync_running,
            "last_sync_time": self._last_sync_time.isoformat() if self._last_sync_time else None,
            "total_synced": len(self._external_id_mapping),
            "sync_history_count": len(self._sync_history),
            "last_result": self._sync_history[-1].to_dict() if self._sync_history else None,
            "config": self.config.to_dict(),
        }

    def get_sync_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """获取同步历史"""
        return [r.to_dict() for r in self._sync_history[-limit:]]

    def set_adapter(self, adapter: SyncAdapter):
        """设置同步适配器"""
        self.adapter = adapter
        logger.info("Sync adapter updated: %s", type(adapter).__name__)


# 全局同步服务单例
_global_sync_service: CapabilitySyncService | None = None
_global_sync_lock = None


def get_global_sync_service() -> CapabilitySyncService:
    """获取全局同步服务单例"""
    global _global_sync_service, _global_sync_lock
    if _global_sync_lock is None:
        from threading import Lock

        _global_sync_lock = Lock()

    if _global_sync_service is None:
        with _global_sync_lock:
            if _global_sync_service is None:
                _global_sync_service = CapabilitySyncService()
    return _global_sync_service
