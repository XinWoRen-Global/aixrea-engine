"""
子Agent集成模块（Subagent Integration）
=======================================

负责将现有subagents/registry.py中的子Agent自动集成到统一能力注册中心。

功能：
1. 扫描所有已注册的子Agent（内置 + 自定义）
2. 将子Agent配置转换为CapabilityMetadata
3. 注册到统一能力注册中心
4. 支持增量同步
"""

import logging
import time
from typing import Any

from deerflow.capability.integrations.coordinator import (
    IntegrationResult,
    IntegrationStatus,
)
from deerflow.capability.registry import (
    CapabilityMetadata,
    CapabilityRegistry,
    CapabilityType,
)

logger = logging.getLogger(__name__)


class SubagentIntegration:
    """
    子Agent集成器

    负责将现有subagents/registry.py中的子Agent自动集成到统一能力注册中心。
    """

    def __init__(self, registry: CapabilityRegistry):
        self.registry = registry
        self._registered_agents: set[str] = set()
        self._last_sync_time: float | None = None

    def sync(self) -> IntegrationResult:
        """
        同步所有子Agent到统一能力注册中心

        Returns:
            集成结果
        """
        result = IntegrationResult(
            integration_name="subagent",
            status=IntegrationStatus.SYNCING,
        )

        try:
            logger.info("Starting subagent integration...")

            # 1. 获取所有内置子Agent
            builtin_agents = self._get_builtin_subagents()

            # 2. 获取所有自定义子Agent
            custom_agents = self._get_custom_subagents()

            # 3. 合并并去重
            all_agents = {}
            all_agents.update(builtin_agents)
            all_agents.update(custom_agents)

            logger.info("Found %d subagents (%d builtin, %d custom)", len(all_agents), len(builtin_agents), len(custom_agents))

            # 4. 转换并注册
            registered_count = 0
            failed_count = 0
            skipped_count = 0

            for name, config in all_agents.items():
                try:
                    # 检查是否已注册
                    if self.registry.get(name, CapabilityType.AGENT):
                        skipped_count += 1
                        continue

                    # 转换为CapabilityMetadata
                    metadata = self._convert_to_metadata(name, config)

                    # 注册
                    if self.registry.register(metadata):
                        registered_count += 1
                        self._registered_agents.add(name)
                    else:
                        failed_count += 1

                except Exception as e:
                    logger.error("Failed to register subagent %s: %s", name, e, exc_info=True)
                    failed_count += 1

            result.registered_count = registered_count
            result.failed_count = failed_count
            result.skipped_count = skipped_count
            result.status = IntegrationStatus.COMPLETED
            result.completed_at = time.time()

            logger.info("Subagent integration completed: %d registered, %d failed, %d skipped", registered_count, failed_count, skipped_count)

        except Exception as e:
            result.status = IntegrationStatus.FAILED
            result.error_message = str(e)
            result.completed_at = time.time()
            logger.error("Subagent integration failed: %s", e, exc_info=True)

        self._last_sync_time = time.time()
        return result

    def _get_builtin_subagents(self) -> dict[str, Any]:
        """获取所有内置子Agent"""
        try:
            from deerflow.subagents.builtins import BUILTIN_SUBAGENTS

            return dict(BUILTIN_SUBAGENTS)
        except ImportError as e:
            logger.warning("Failed to import builtin subagents: %s", e)
            return {}
        except Exception as e:
            logger.error("Failed to get builtin subagents: %s", e, exc_info=True)
            return {}

    def _get_custom_subagents(self) -> dict[str, Any]:
        """获取所有自定义子Agent"""
        try:
            from deerflow.config.subagents_config import get_subagents_app_config
            from deerflow.subagents.registry import get_subagent_config

            app_config = get_subagents_app_config()
            custom_agents = {}

            # 从custom_agents配置中获取
            if hasattr(app_config, "custom_agents"):
                for name, config in app_config.custom_agents.items():
                    subagent_config = get_subagent_config(name)
                    if subagent_config:
                        custom_agents[name] = subagent_config

            return custom_agents

        except ImportError as e:
            logger.warning("Failed to import custom subagents: %s", e)
            return {}
        except Exception as e:
            logger.error("Failed to get custom subagents: %s", e, exc_info=True)
            return {}

    def _convert_to_metadata(self, name: str, config: Any) -> CapabilityMetadata:
        """
        将子Agent配置转换为CapabilityMetadata

        Args:
            name: Agent名称
            config: Agent配置

        Returns:
            CapabilityMetadata
        """
        # 提取配置信息
        description = getattr(config, "description", f"Subagent: {name}")
        model = getattr(config, "model", None)
        tools = getattr(config, "tools", [])
        skills = getattr(config, "skills", [])
        max_turns = getattr(config, "max_turns", None)
        timeout_seconds = getattr(config, "timeout_seconds", None)

        # 推断业务域
        domain = self._infer_domain(name, description)

        # 推断标签
        tags = self._infer_tags(name, description, tools, skills)

        # 构建元数据
        metadata = CapabilityMetadata(
            name=name,
            type=CapabilityType.AGENT,
            description=description,
            version="1.0.0",
            domain=domain,
            tags=tags,
            categories=["agent", "subagent"],
            status="active",
            is_builtin=self._is_builtin(name),
            metadata={
                "model": model,
                "tools": list(tools) if tools else [],
                "skills": list(skills) if skills else [],
                "max_turns": max_turns,
                "timeout_seconds": timeout_seconds,
                "source": "subagent_registry",
            },
        )

        return metadata

    def _infer_domain(self, name: str, description: str) -> str:
        """推断业务域"""
        name_lower = name.lower()
        desc_lower = description.lower()

        # 内容创作域
        content_keywords = ["drama", "novel", "comic", "music", "interactive", "script", "video", "image", "audio", "创作", "短剧", "小说", "漫画", "音乐"]
        if any(k in name_lower or k in desc_lower for k in content_keywords):
            return "content_creation"

        # 商城交易域
        marketplace_keywords = ["product", "order", "payment", "refund", "shop", "marketplace", "商品", "订单", "支付", "退款", "商城"]
        if any(k in name_lower or k in desc_lower for k in marketplace_keywords):
            return "marketplace"

        # 用户增长域
        growth_keywords = ["growth", "user", "acquisition", "retention", "recommendation", "用户", "增长", "获客", "留存", "推荐"]
        if any(k in name_lower or k in desc_lower for k in growth_keywords):
            return "growth"

        # 分发运营域
        distribution_keywords = ["distribution", "ops", "campaign", "content_operations", "分发", "运营", "活动"]
        if any(k in name_lower or k in desc_lower for k in distribution_keywords):
            return "distribution"

        # 客服支持域
        support_keywords = ["support", "customer", "ticket", "knowledge", "客服", "工单", "知识库"]
        if any(k in name_lower or k in desc_lower for k in support_keywords):
            return "support"

        # 数据智能域
        data_keywords = ["data", "analytics", "intelligence", "analysis", "report", "数据", "分析", "智能", "报表"]
        if any(k in name_lower or k in desc_lower for k in data_keywords):
            return "data"

        return "general"

    def _infer_tags(self, name: str, description: str, tools: list[str], skills: list[str]) -> list[str]:
        """推断标签"""
        tags = []

        # 从名称推断
        name_lower = name.lower()
        if "drama" in name_lower or "短剧" in name:
            tags.append("短剧")
        if "novel" in name_lower or "小说" in name:
            tags.append("小说")
        if "comic" in name_lower or "漫画" in name:
            tags.append("漫画")
        if "music" in name_lower or "音乐" in name:
            tags.append("音乐")
        if "interactive" in name_lower or "互动" in name:
            tags.append("互动")

        # 从工具推断
        if tools:
            tags.extend([t for t in tools if len(t) < 20][:5])

        # 从Skill推断
        if skills:
            tags.extend([s for s in skills if len(s) < 20][:5])

        # 去重
        return list(set(tags))[:10]

    def _is_builtin(self, name: str) -> bool:
        """判断是否为内置Agent"""
        try:
            from deerflow.subagents.builtins import BUILTIN_SUBAGENTS

            return name in BUILTIN_SUBAGENTS
        except Exception:
            return False

    def get_registered_agents(self) -> set[str]:
        """获取已注册的Agent集合"""
        return set(self._registered_agents)

    @property
    def last_sync_time(self) -> float | None:
        """获取最后同步时间"""
        return self._last_sync_time
