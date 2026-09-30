"""
能力同步模块（Capability Sync）
================================

负责Deerflow能力注册中心与外部系统（如InsForge agent_registrations表）的双向同步。

功能：
1. Deerflow能力注册中心 → 外部系统的同步
2. 外部系统 → Deerflow能力注册中心的同步
3. 增量同步和全量同步
4. 同步状态跟踪和冲突解决
5. 自动同步（后台定时任务）
6. 配置管理
"""

from deerflow.capability.sync.adapter import (
    ExternalCapability,
    InsForgeAdapter,
    SyncAdapter,
)
from deerflow.capability.sync.config import (
    SyncConfig,
    get_sync_config,
    reload_sync_config,
)
from deerflow.capability.sync.service import (
    CapabilitySyncService,
    SyncDirection,
    SyncMode,
    SyncResult,
    get_global_sync_service,
)

__all__ = [
    # 同步服务
    "CapabilitySyncService",
    "SyncDirection",
    "SyncMode",
    "SyncResult",
    "get_global_sync_service",
    # 适配器
    "SyncAdapter",
    "InsForgeAdapter",
    "ExternalCapability",
    # 配置
    "SyncConfig",
    "get_sync_config",
    "reload_sync_config",
]
