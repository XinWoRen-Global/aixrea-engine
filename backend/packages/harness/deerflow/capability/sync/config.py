"""
能力同步配置（Capability Sync Config）
======================================

管理能力同步服务的配置，包括：
1. 数据库连接配置
2. 同步策略配置
3. 环境变量读取
"""

import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SyncConfig:
    """能力同步配置"""

    # 数据库连接
    insforge_database_url: str = field(default="")
    insforge_api_key: str = field(default="")
    insforge_base_url: str = field(default="https://api.insforge.dev")
    insforge_table_name: str = field(default="agent_registrations")

    # 同步策略
    sync_enabled: bool = field(default=True)
    sync_direction: str = field(default="bidirectional")  # to_external, from_external, bidirectional
    sync_mode: str = field(default="incremental")  # full, incremental
    sync_interval_seconds: int = field(default=300)  # 5分钟
    sync_on_startup: bool = field(default=True)

    # 冲突解决策略
    conflict_resolution: str = field(default="external_wins")  # external_wins, local_wins, manual

    # 批量配置
    batch_size: int = field(default=50)
    max_retries: int = field(default=3)
    retry_delay_seconds: int = field(default=5)

    # 日志配置
    log_sync_details: bool = field(default=False)

    @classmethod
    def from_env(cls) -> "SyncConfig":
        """从环境变量加载配置"""
        return cls(
            insforge_database_url=os.environ.get("INSFORGE_DATABASE_URL", ""),
            insforge_api_key=os.environ.get("INSFORGE_API_KEY", ""),
            insforge_base_url=os.environ.get("INSFORGE_BASE_URL", "https://api.insforge.dev"),
            insforge_table_name=os.environ.get("INSFORGE_TABLE_NAME", "agent_registrations"),
            sync_enabled=os.environ.get("CAPABILITY_SYNC_ENABLED", "true").lower() == "true",
            sync_direction=os.environ.get("CAPABILITY_SYNC_DIRECTION", "bidirectional"),
            sync_mode=os.environ.get("CAPABILITY_SYNC_MODE", "incremental"),
            sync_interval_seconds=int(os.environ.get("CAPABILITY_SYNC_INTERVAL", "300")),
            sync_on_startup=os.environ.get("CAPABILITY_SYNC_ON_STARTUP", "true").lower() == "true",
            conflict_resolution=os.environ.get("CAPABILITY_SYNC_CONFLICT_RESOLUTION", "external_wins"),
            batch_size=int(os.environ.get("CAPABILITY_SYNC_BATCH_SIZE", "50")),
            max_retries=int(os.environ.get("CAPABILITY_SYNC_MAX_RETRIES", "3")),
            retry_delay_seconds=int(os.environ.get("CAPABILITY_SYNC_RETRY_DELAY", "5")),
            log_sync_details=os.environ.get("CAPABILITY_SYNC_LOG_DETAILS", "false").lower() == "true",
        )

    def validate(self) -> tuple[bool, list[str]]:
        """验证配置，返回(是否有效, 错误列表)"""
        errors = []

        if not self.insforge_database_url and not self.insforge_api_key:
            errors.append("Neither INSFORGE_DATABASE_URL nor INSFORGE_API_KEY is configured")

        if self.sync_direction not in ["to_external", "from_external", "bidirectional"]:
            errors.append(f"Invalid sync_direction: {self.sync_direction}")

        if self.sync_mode not in ["full", "incremental"]:
            errors.append(f"Invalid sync_mode: {self.sync_mode}")

        if self.conflict_resolution not in ["external_wins", "local_wins", "manual"]:
            errors.append(f"Invalid conflict_resolution: {self.conflict_resolution}")

        if self.sync_interval_seconds < 60:
            errors.append("sync_interval_seconds must be at least 60 seconds")

        return len(errors) == 0, errors

    def to_dict(self) -> dict:
        """转换为字典（隐藏敏感信息）"""
        return {
            "sync_enabled": self.sync_enabled,
            "sync_direction": self.sync_direction,
            "sync_mode": self.sync_mode,
            "sync_interval_seconds": self.sync_interval_seconds,
            "sync_on_startup": self.sync_on_startup,
            "conflict_resolution": self.conflict_resolution,
            "batch_size": self.batch_size,
            "max_retries": self.max_retries,
            "use_direct_db": bool(self.insforge_database_url),
            "use_api": bool(self.insforge_api_key),
            "table_name": self.insforge_table_name,
        }


# 全局配置单例
_global_config: SyncConfig | None = None


def get_sync_config() -> SyncConfig:
    """获取全局同步配置"""
    global _global_config
    if _global_config is None:
        _global_config = SyncConfig.from_env()
        is_valid, errors = _global_config.validate()
        if not is_valid:
            logger.warning("Sync config validation warnings: %s", errors)
    return _global_config


def reload_sync_config() -> SyncConfig:
    """重新加载同步配置"""
    global _global_config
    _global_config = SyncConfig.from_env()
    logger.info("Sync config reloaded")
    return _global_config
