"""
统一能力注册中心（Unified Capability Registry）
=================================================

基于"统一智能底座，分域自动演进，能力自动复用"原则设计。

核心功能：
1. 统一注册所有类型的能力：Agent、工具、Skill、模型
2. 能力发现与推荐：新Agent创建时自动推荐可复用能力
3. 能力版本管理：版本控制、灰度发布、回滚机制
4. 能力使用统计：自动统计能力使用情况，优化能力分配

架构设计：
- CapabilityType: 能力类型枚举（AGENT, TOOL, SKILL, MODEL）
- CapabilityMetadata: 能力元数据
- CapabilityRegistry: 统一能力注册中心
- CapabilityDiscovery: 能力发现与推荐引擎
- CapabilityVersionManager: 能力版本管理器
- CapabilityUsageTracker: 能力使用统计器
"""

from deerflow.capability.discovery import (
    CapabilityDiscovery,
    CapabilityRecommendation,
)
from deerflow.capability.registry import (
    CapabilityMetadata,
    CapabilityRegistry,
    CapabilityType,
    get_global_registry,
)
from deerflow.capability.usage import (
    CapabilityUsage,
    CapabilityUsageTracker,
    UsageMetrics,
)
from deerflow.capability.version import (
    CapabilityVersion,
    CapabilityVersionManager,
    VersionStatus,
)

__all__ = [
    # 核心类型
    "CapabilityType",
    "CapabilityMetadata",
    "CapabilityRegistry",
    "get_global_registry",
    # 能力发现
    "CapabilityDiscovery",
    "CapabilityRecommendation",
    # 版本管理
    "CapabilityVersion",
    "CapabilityVersionManager",
    "VersionStatus",
    # 使用统计
    "CapabilityUsage",
    "CapabilityUsageTracker",
    "UsageMetrics",
]

__version__ = "1.0.0"
