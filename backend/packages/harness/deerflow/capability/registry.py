"""
统一能力注册中心（Unified Capability Registry）
=================================================

负责注册、存储、查询所有类型的能力（Agent、工具、Skill、模型）。

设计原则：
1. 统一注册：所有能力类型使用统一的注册接口
2. 元数据丰富：每个能力都有完整的元数据（描述、输入输出、性能指标、使用统计）
3. 分类管理：按能力类型、业务域、标签进行分类管理
4. 快速查询：支持按名称、类型、标签、业务域等多维度查询
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)


class CapabilityType(Enum):
    """能力类型枚举"""

    AGENT = "agent"
    TOOL = "tool"
    SKILL = "skill"
    MODEL = "model"
    WORKFLOW = "workflow"
    DATASET = "dataset"


@dataclass
class CapabilityMetadata:
    """能力元数据"""

    # 基本信息
    name: str
    type: CapabilityType
    description: str
    version: str = "1.0.0"

    # 分类信息
    domain: str = "general"  # 业务域：content_creation, marketplace, growth, etc.
    tags: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)

    # 能力规格
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    required_permissions: list[str] = field(default_factory=list)

    # 性能指标
    avg_latency_ms: float | None = None
    success_rate: float | None = None
    cost_per_call: float | None = None

    # 状态信息
    status: str = "active"  # active, deprecated, experimental
    is_builtin: bool = False
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    # 扩展信息
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "type": self.type.value,
            "description": self.description,
            "version": self.version,
            "domain": self.domain,
            "tags": self.tags,
            "categories": self.categories,
            "status": self.status,
            "is_builtin": self.is_builtin,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }


class CapabilityRegistry:
    """
    统一能力注册中心

    负责注册、存储、查询所有类型的能力。
    线程安全，支持并发访问。
    """

    def __init__(self):
        self._capabilities: dict[str, CapabilityMetadata] = {}
        self._lock = Lock()
        self._domain_index: dict[str, set[str]] = {}
        self._type_index: dict[CapabilityType, set[str]] = {}
        self._tag_index: dict[str, set[str]] = {}

    def register(self, metadata: CapabilityMetadata) -> bool:
        """
        注册能力

        Args:
            metadata: 能力元数据

        Returns:
            是否注册成功
        """
        with self._lock:
            key = self._make_key(metadata.name, metadata.type)

            if key in self._capabilities:
                logger.warning("Capability already registered: %s (type=%s)", metadata.name, metadata.type.value)
                return False

            self._capabilities[key] = metadata
            self._update_indexes(key, metadata)

            logger.info("Capability registered: %s (type=%s, domain=%s)", metadata.name, metadata.type.value, metadata.domain)
            return True

    def unregister(self, name: str, type: CapabilityType) -> bool:
        """
        注销能力

        Args:
            name: 能力名称
            type: 能力类型

        Returns:
            是否注销成功
        """
        with self._lock:
            key = self._make_key(name, type)

            if key not in self._capabilities:
                return False

            metadata = self._capabilities.pop(key)
            self._remove_from_indexes(key, metadata)

            logger.info("Capability unregistered: %s (type=%s)", name, type.value)
            return True

    def get(self, name: str, type: CapabilityType) -> CapabilityMetadata | None:
        """
        获取能力元数据

        Args:
            name: 能力名称
            type: 能力类型

        Returns:
            能力元数据，不存在返回None
        """
        key = self._make_key(name, type)
        return self._capabilities.get(key)

    def list_by_type(self, type: CapabilityType) -> list[CapabilityMetadata]:
        """按类型列出所有能力"""
        keys = self._type_index.get(type, set())
        return [self._capabilities[k] for k in keys if k in self._capabilities]

    def list_by_domain(self, domain: str) -> list[CapabilityMetadata]:
        """按业务域列出所有能力"""
        keys = self._domain_index.get(domain, set())
        return [self._capabilities[k] for k in keys if k in self._capabilities]

    def list_by_tag(self, tag: str) -> list[CapabilityMetadata]:
        """按标签列出所有能力"""
        keys = self._tag_index.get(tag, set())
        return [self._capabilities[k] for k in keys if k in self._capabilities]

    def search(self, query: str | None = None, type: CapabilityType | None = None, domain: str | None = None, tags: list[str] | None = None, status: str | None = None) -> list[CapabilityMetadata]:
        """
        多维度搜索能力

        Args:
            query: 搜索关键词（匹配名称和描述）
            type: 能力类型
            domain: 业务域
            tags: 标签列表
            status: 状态

        Returns:
            匹配的能力列表
        """
        results = list(self._capabilities.values())

        if query:
            query_lower = query.lower()
            results = [c for c in results if query_lower in c.name.lower() or query_lower in c.description.lower()]

        if type:
            results = [c for c in results if c.type == type]

        if domain:
            results = [c for c in results if c.domain == domain]

        if tags:
            results = [c for c in results if any(t in c.tags for t in tags)]

        if status:
            results = [c for c in results if c.status == status]

        return results

    def get_all(self) -> list[CapabilityMetadata]:
        """获取所有已注册的能力"""
        return list(self._capabilities.values())

    def get_statistics(self) -> dict[str, Any]:
        """获取注册中心统计信息"""
        type_counts = {}
        for t in CapabilityType:
            type_counts[t.value] = len(self._type_index.get(t, set()))

        domain_counts = {}
        for domain, keys in self._domain_index.items():
            domain_counts[domain] = len(keys)

        return {
            "total_capabilities": len(self._capabilities),
            "by_type": type_counts,
            "by_domain": domain_counts,
            "total_tags": len(self._tag_index),
        }

    _KEY_SEP = "\x1e"  # ASCII record separator — never appears in capability names

    def _make_key(self, name: str, type: CapabilityType) -> str:
        """生成能力唯一键（使用不可见分隔符避免名称碰撞）"""
        return f"{type.value}{self._KEY_SEP}{name}"

    def _update_indexes(self, key: str, metadata: CapabilityMetadata):
        """更新索引"""
        # 类型索引
        if metadata.type not in self._type_index:
            self._type_index[metadata.type] = set()
        self._type_index[metadata.type].add(key)

        # 业务域索引
        if metadata.domain not in self._domain_index:
            self._domain_index[metadata.domain] = set()
        self._domain_index[metadata.domain].add(key)

        # 标签索引
        for tag in metadata.tags:
            if tag not in self._tag_index:
                self._tag_index[tag] = set()
            self._tag_index[tag].add(key)

    def _remove_from_indexes(self, key: str, metadata: CapabilityMetadata):
        """从索引中移除"""
        # 类型索引
        if metadata.type in self._type_index:
            self._type_index[metadata.type].discard(key)

        # 业务域索引
        if metadata.domain in self._domain_index:
            self._domain_index[metadata.domain].discard(key)

        # 标签索引
        for tag in metadata.tags:
            if tag in self._tag_index:
                self._tag_index[tag].discard(key)


# 全局注册中心单例
_global_registry: CapabilityRegistry | None = None
_global_registry_lock = Lock()


def get_global_registry() -> CapabilityRegistry:
    """获取全局能力注册中心单例"""
    global _global_registry
    if _global_registry is None:
        with _global_registry_lock:
            if _global_registry is None:
                _global_registry = CapabilityRegistry()
    return _global_registry
