"""
能力版本管理器（Capability Version Manager）
=============================================

负责能力的版本控制、灰度发布、回滚机制。

核心功能：
1. 版本注册与管理
2. 版本状态管理（draft, testing, active, deprecated, archived）
3. 灰度发布（按比例、按用户组、按业务域）
4. 版本回滚
5. 版本兼容性检查
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Any

from deerflow.capability.registry import CapabilityType

logger = logging.getLogger(__name__)


class VersionStatus(Enum):
    """版本状态枚举"""

    DRAFT = "draft"  # 草稿
    TESTING = "testing"  # 测试中
    ACTIVE = "active"  # 活跃
    DEPRECATED = "deprecated"  # 已弃用
    ARCHIVED = "archived"  # 已归档


@dataclass
class CapabilityVersion:
    """能力版本"""

    capability_name: str
    capability_type: CapabilityType
    version: str
    status: VersionStatus = VersionStatus.DRAFT

    # 版本信息
    changelog: str = ""
    release_notes: str = ""
    breaking_changes: list[str] = field(default_factory=list)

    # 灰度发布配置
    rollout_percentage: float = 0.0  # 灰度比例 0-100
    rollout_domains: list[str] = field(default_factory=list)  # 灰度业务域
    rollout_user_groups: list[str] = field(default_factory=list)  # 灰度用户组

    # 兼容性
    compatible_versions: list[str] = field(default_factory=list)
    min_compatible_version: str | None = None

    # 元数据
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    released_at: float | None = None
    deprecated_at: float | None = None

    # 扩展信息
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_name": self.capability_name,
            "capability_type": self.capability_type.value,
            "version": self.version,
            "status": self.status.value,
            "changelog": self.changelog,
            "rollout_percentage": self.rollout_percentage,
            "rollout_domains": self.rollout_domains,
            "compatible_versions": self.compatible_versions,
            "created_at": self.created_at,
            "released_at": self.released_at,
        }


class CapabilityVersionManager:
    """
    能力版本管理器

    负责能力的版本控制、灰度发布、回滚机制。
    线程安全。
    """

    def __init__(self):
        self._versions: dict[str, list[CapabilityVersion]] = {}
        self._lock = Lock()
        self._active_versions: dict[str, str] = {}  # capability_key -> active version

    def register_version(self, version: CapabilityVersion) -> bool:
        """
        注册新版本

        Args:
            version: 能力版本

        Returns:
            是否注册成功
        """
        with self._lock:
            key = self._make_key(version.capability_name, version.capability_type)

            if key not in self._versions:
                self._versions[key] = []

            # 检查版本是否已存在
            existing = [v for v in self._versions[key] if v.version == version.version]
            if existing:
                logger.warning("Version already exists: %s %s", version.capability_name, version.version)
                return False

            self._versions[key].append(version)
            # 按版本号排序
            self._versions[key].sort(key=lambda v: self._version_to_tuple(v.version), reverse=True)

            logger.info("Version registered: %s %s (status=%s)", version.capability_name, version.version, version.status.value)
            return True

    def promote_version(self, capability_name: str, capability_type: CapabilityType, version: str, new_status: VersionStatus, rollout_percentage: float | None = None) -> bool:
        """
        升级版本状态

        Args:
            capability_name: 能力名称
            capability_type: 能力类型
            version: 版本号
            new_status: 新状态
            rollout_percentage: 灰度比例（可选）

        Returns:
            是否升级成功
        """
        with self._lock:
            key = self._make_key(capability_name, capability_type)

            if key not in self._versions:
                return False

            target_version = None
            for v in self._versions[key]:
                if v.version == version:
                    target_version = v
                    break

            if not target_version:
                return False

            # 更新状态
            old_status = target_version.status
            target_version.status = new_status
            target_version.updated_at = time.time()

            if rollout_percentage is not None:
                target_version.rollout_percentage = rollout_percentage

            # 如果设置为active，更新活跃版本
            if new_status == VersionStatus.ACTIVE:
                target_version.released_at = time.time()
                self._active_versions[key] = version

                # 将其他active版本设置为deprecated
                for v in self._versions[key]:
                    if v.version != version and v.status == VersionStatus.ACTIVE:
                        v.status = VersionStatus.DEPRECATED
                        v.deprecated_at = time.time()

            logger.info("Version promoted: %s %s (%s -> %s)", capability_name, version, old_status.value, new_status.value)
            return True

    def rollback_version(self, capability_name: str, capability_type: CapabilityType, target_version: str) -> bool:
        """
        回滚到指定版本

        Args:
            capability_name: 能力名称
            capability_type: 能力类型
            target_version: 目标版本号

        Returns:
            是否回滚成功
        """
        return self.promote_version(capability_name, capability_type, target_version, VersionStatus.ACTIVE)

    def get_active_version(self, capability_name: str, capability_type: CapabilityType) -> CapabilityVersion | None:
        """获取当前活跃版本"""
        key = self._make_key(capability_name, capability_type)
        active_version = self._active_versions.get(key)

        if not active_version:
            return None

        return self.get_version(capability_name, capability_type, active_version)

    def get_version(self, capability_name: str, capability_type: CapabilityType, version: str) -> CapabilityVersion | None:
        """获取指定版本"""
        key = self._make_key(capability_name, capability_type)

        if key not in self._versions:
            return None

        for v in self._versions[key]:
            if v.version == version:
                return v

        return None

    def list_versions(self, capability_name: str, capability_type: CapabilityType, status: VersionStatus | None = None) -> list[CapabilityVersion]:
        """列出所有版本"""
        key = self._make_key(capability_name, capability_type)

        if key not in self._versions:
            return []

        versions = self._versions[key]

        if status:
            versions = [v for v in versions if v.status == status]

        return versions

    def should_use_version(self, capability_name: str, capability_type: CapabilityType, version: str, domain: str | None = None, user_group: str | None = None, user_id: str | None = None) -> bool:
        """
        判断是否应该使用指定版本（灰度发布判断）

        Args:
            capability_name: 能力名称
            capability_type: 能力类型
            version: 版本号
            domain: 业务域
            user_group: 用户组
            user_id: 用户ID

        Returns:
            是否应该使用该版本
        """
        version_info = self.get_version(capability_name, capability_type, version)

        if not version_info:
            return False

        # 如果是active状态且灰度100%，直接使用
        if version_info.status == VersionStatus.ACTIVE and version_info.rollout_percentage >= 100:
            return True

        # 如果是testing状态，需要检查灰度条件
        if version_info.status in [VersionStatus.TESTING, VersionStatus.ACTIVE]:
            # 检查业务域灰度
            if domain and version_info.rollout_domains:
                if domain in version_info.rollout_domains:
                    return True

            # 检查用户组灰度
            if user_group and version_info.rollout_user_groups:
                if user_group in version_info.rollout_user_groups:
                    return True

            # 按比例灰度（基于user_id哈希）
            if version_info.rollout_percentage > 0 and user_id:
                user_hash = hash(user_id) % 100
                if user_hash < version_info.rollout_percentage:
                    return True

        return False

    def check_compatibility(self, capability_name: str, capability_type: CapabilityType, version1: str, version2: str) -> tuple[bool, list[str]]:
        """
        检查两个版本的兼容性

        Returns:
            (是否兼容, 不兼容原因列表)
        """
        v1 = self.get_version(capability_name, capability_type, version1)
        v2 = self.get_version(capability_name, capability_type, version2)

        if not v1 or not v2:
            return False, ["版本不存在"]

        issues = []

        # 检查v2是否在v1的兼容列表中
        if v2.version not in v1.compatible_versions:
            issues.append(f"{version2} 不在 {version1} 的兼容列表中")

        # 检查破坏性变更
        if v2.breaking_changes:
            issues.append(f"{version2} 包含破坏性变更: {v2.breaking_changes}")

        return len(issues) == 0, issues

    _KEY_SEP = "\x1e"  # 与 registry.py 一致，避免名称碰撞

    def _make_key(self, name: str, type: CapabilityType) -> str:
        return f"{type.value}{self._KEY_SEP}{name}"

    def _version_to_tuple(self, version: str) -> tuple:
        """将版本号转换为元组用于比较"""
        try:
            parts = version.split(".")
            return tuple(int(p) for p in parts)
        except (ValueError, AttributeError):
            return (0, 0, 0)


# 全局版本管理器单例
_global_version_manager: CapabilityVersionManager | None = None
_global_version_manager_lock = Lock()


def get_global_version_manager() -> CapabilityVersionManager:
    """获取全局版本管理器单例"""
    global _global_version_manager
    if _global_version_manager is None:
        with _global_version_manager_lock:
            if _global_version_manager is None:
                _global_version_manager = CapabilityVersionManager()
    return _global_version_manager
