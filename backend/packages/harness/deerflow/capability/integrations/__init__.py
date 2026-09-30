"""
能力平台集成模块（Capability Platform Integrations）
=====================================================

负责将现有系统的能力（子Agent、工具、Skill、模型）自动集成到统一能力注册中心。

集成子系统：
1. SubagentIntegration - 与现有subagents/registry.py集成
2. ToolIntegration - 与现有tools系统集成
3. SkillIntegration - 与现有skills系统集成
4. ModelIntegration - 与现有模型系统集成
5. UsageIntegration - 运行时使用统计集成
"""

from deerflow.capability.integrations.coordinator import (
    CapabilityPlatformIntegration,
    IntegrationResult,
    IntegrationStatus,
)
from deerflow.capability.integrations.skill import SkillIntegration
from deerflow.capability.integrations.subagent import SubagentIntegration
from deerflow.capability.integrations.tool import ToolIntegration
from deerflow.capability.integrations.usage import UsageIntegration

__all__ = [
    # 核心协调器
    "CapabilityPlatformIntegration",
    "IntegrationStatus",
    "IntegrationResult",
    # 子系统集成
    "SubagentIntegration",
    "ToolIntegration",
    "SkillIntegration",
    "UsageIntegration",
]
