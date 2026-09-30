"""
Skill集成模块（Skill Integration）
===================================

负责将现有skills系统中的Skill自动集成到统一能力注册中心。

功能：
1. 扫描所有已安装的Skill
2. 将Skill配置转换为CapabilityMetadata
3. 注册到统一能力注册中心
4. 支持增量同步
"""

import logging
import os
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


class SkillIntegration:
    """
    Skill集成器

    负责将现有skills系统中的Skill自动集成到统一能力注册中心。
    """

    def __init__(self, registry: CapabilityRegistry):
        self.registry = registry
        self._registered_skills: set[str] = set()
        self._last_sync_time: float | None = None

    def sync(self) -> IntegrationResult:
        """
        同步所有Skill到统一能力注册中心

        Returns:
            集成结果
        """
        result = IntegrationResult(
            integration_name="skill",
            status=IntegrationStatus.SYNCING,
        )

        try:
            logger.info("Starting skill integration...")

            # 1. 获取所有已安装的Skill
            skills = self._get_all_skills()

            logger.info("Found %d skills", len(skills))

            # 2. 转换并注册
            registered_count = 0
            failed_count = 0
            skipped_count = 0

            for name, skill_info in skills.items():
                try:
                    # 检查是否已注册
                    if self.registry.get(name, CapabilityType.SKILL):
                        skipped_count += 1
                        continue

                    # 转换为CapabilityMetadata
                    metadata = self._convert_to_metadata(name, skill_info)

                    # 注册
                    if self.registry.register(metadata):
                        registered_count += 1
                        self._registered_skills.add(name)
                    else:
                        failed_count += 1

                except Exception as e:
                    logger.error("Failed to register skill %s: %s", name, e, exc_info=True)
                    failed_count += 1

            result.registered_count = registered_count
            result.failed_count = failed_count
            result.skipped_count = skipped_count
            result.status = IntegrationStatus.COMPLETED
            result.completed_at = time.time()

            logger.info("Skill integration completed: %d registered, %d failed, %d skipped", registered_count, failed_count, skipped_count)

        except Exception as e:
            result.status = IntegrationStatus.FAILED
            result.error_message = str(e)
            result.completed_at = time.time()
            logger.error("Skill integration failed: %s", e, exc_info=True)

        self._last_sync_time = time.time()
        return result

    def _get_all_skills(self) -> dict[str, Any]:
        """获取所有已安装的Skill"""
        skills = {}

        # 1. 从Skill存储获取
        try:
            from deerflow.skills.storage import get_skill_storage

            storage = get_skill_storage()
            if hasattr(storage, "list_skills"):
                skill_list = storage.list_skills()
                for skill in skill_list:
                    name = getattr(skill, "name", None) or skill.get("name")
                    if name:
                        skills[name] = {
                            "name": name,
                            "description": getattr(skill, "description", skill.get("description", f"Skill: {name}")),
                            "skill_obj": skill,
                            "source": "skill_storage",
                        }
        except ImportError:
            logger.debug("Skill storage not available")
        except Exception as e:
            logger.debug("Failed to get skills from storage: %s", e)

        # 2. 扫描内置Skill目录
        try:
            import deerflow

            deerflow_path = os.path.dirname(deerflow.__file__)
            skills_dir = os.path.join(deerflow_path, "skills")

            if os.path.exists(skills_dir):
                for item in os.listdir(skills_dir):
                    item_path = os.path.join(skills_dir, item)
                    if os.path.isdir(item_path):
                        skill_md = os.path.join(item_path, "SKILL.md")
                        if os.path.exists(skill_md):
                            name = item
                            if name not in skills:
                                description = self._read_skill_description(skill_md)
                                skills[name] = {
                                    "name": name,
                                    "description": description,
                                    "path": item_path,
                                    "is_builtin": True,
                                    "source": "builtin_skills",
                                }
        except Exception as e:
            logger.debug("Failed to scan builtin skills: %s", e)

        # 3. 扫描用户Skill目录
        try:
            user_skills_dir = os.path.expanduser("~/.deerflow/skills")
            if os.path.exists(user_skills_dir):
                for item in os.listdir(user_skills_dir):
                    item_path = os.path.join(user_skills_dir, item)
                    if os.path.isdir(item_path):
                        skill_md = os.path.join(item_path, "SKILL.md")
                        if os.path.exists(skill_md):
                            name = item
                            if name not in skills:
                                description = self._read_skill_description(skill_md)
                                skills[name] = {
                                    "name": name,
                                    "description": description,
                                    "path": item_path,
                                    "is_builtin": False,
                                    "source": "user_skills",
                                }
        except Exception as e:
            logger.debug("Failed to scan user skills: %s", e)

        return skills

    def _read_skill_description(self, skill_md_path: str) -> str:
        """读取Skill描述"""
        try:
            with open(skill_md_path, encoding="utf-8") as f:
                content = f.read(500)  # 只读取前500字符

                # 尝试提取description
                lines = content.split("\n")
                for line in lines:
                    if "description:" in line.lower():
                        return line.split(":", 1)[1].strip()

                # 如果没有description，返回第一行非空内容
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        return line[:100]

                return "Skill"
        except Exception:
            return "Skill"

    def _convert_to_metadata(self, name: str, skill_info: dict[str, Any]) -> CapabilityMetadata:
        """
        将Skill配置转换为CapabilityMetadata

        Args:
            name: Skill名称
            skill_info: Skill信息

        Returns:
            CapabilityMetadata
        """
        description = skill_info.get("description", f"Skill: {name}")
        is_builtin = skill_info.get("is_builtin", False)
        source = skill_info.get("source", "unknown")
        path = skill_info.get("path")

        # 推断业务域
        domain = self._infer_domain(name, description)

        # 推断标签
        tags = self._infer_tags(name, description)

        # 构建元数据
        metadata = CapabilityMetadata(
            name=name,
            type=CapabilityType.SKILL,
            description=description,
            version="1.0.0",
            domain=domain,
            tags=tags,
            categories=["skill"],
            status="active",
            is_builtin=is_builtin,
            metadata={
                "source": source,
                "path": path,
            },
        )

        return metadata

    def _infer_domain(self, name: str, description: str) -> str:
        """推断业务域"""
        name_lower = name.lower()
        desc_lower = description.lower()

        # 内容创作Skill
        content_keywords = ["content", "creation", "drama", "novel", "comic", "music", "创作", "内容", "短剧", "小说", "漫画", "音乐"]
        if any(k in name_lower or k in desc_lower for k in content_keywords):
            return "content_creation"

        # 商城交易Skill
        marketplace_keywords = ["payment", "order", "product", "shop", "marketplace", "支付", "订单", "商品", "商城"]
        if any(k in name_lower or k in desc_lower for k in marketplace_keywords):
            return "marketplace"

        # 数据智能Skill
        data_keywords = ["data", "analytics", "analysis", "intelligence", "数据", "分析", "智能"]
        if any(k in name_lower or k in desc_lower for k in data_keywords):
            return "data"

        return "general"

    def _infer_tags(self, name: str, description: str) -> list[str]:
        """推断标签"""
        tags = []

        name_lower = name.lower()
        if "xinworen" in name_lower:
            tags.append("xinworen")
        if "content" in name_lower:
            tags.append("content")
        if "payment" in name_lower:
            tags.append("payment")
        if "data" in name_lower:
            tags.append("data")

        # 去重
        return list(set(tags))[:10]

    def get_registered_skills(self) -> set[str]:
        """获取已注册的Skill集合"""
        return set(self._registered_skills)

    @property
    def last_sync_time(self) -> float | None:
        """获取最后同步时间"""
        return self._last_sync_time
