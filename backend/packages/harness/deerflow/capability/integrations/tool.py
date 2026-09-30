"""
工具集成模块（Tool Integration）
=================================

负责将现有tools系统中的工具自动集成到统一能力注册中心。

功能：
1. 扫描所有已注册的工具
2. 将工具配置转换为CapabilityMetadata
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


class ToolIntegration:
    """
    工具集成器

    负责将现有tools系统中的工具自动集成到统一能力注册中心。
    """

    def __init__(self, registry: CapabilityRegistry):
        self.registry = registry
        self._registered_tools: set[str] = set()
        self._last_sync_time: float | None = None

    def sync(self) -> IntegrationResult:
        """
        同步所有工具到统一能力注册中心

        Returns:
            集成结果
        """
        result = IntegrationResult(
            integration_name="tool",
            status=IntegrationStatus.SYNCING,
        )

        try:
            logger.info("Starting tool integration...")

            # 1. 获取所有已注册的工具
            tools = self._get_all_tools()

            logger.info("Found %d tools", len(tools))

            # 2. 转换并注册
            registered_count = 0
            failed_count = 0
            skipped_count = 0

            for name, tool_info in tools.items():
                try:
                    # 检查是否已注册
                    if self.registry.get(name, CapabilityType.TOOL):
                        skipped_count += 1
                        continue

                    # 转换为CapabilityMetadata
                    metadata = self._convert_to_metadata(name, tool_info)

                    # 注册
                    if self.registry.register(metadata):
                        registered_count += 1
                        self._registered_tools.add(name)
                    else:
                        failed_count += 1

                except Exception as e:
                    logger.error("Failed to register tool %s: %s", name, e, exc_info=True)
                    failed_count += 1

            result.registered_count = registered_count
            result.failed_count = failed_count
            result.skipped_count = skipped_count
            result.status = IntegrationStatus.COMPLETED
            result.completed_at = time.time()

            logger.info("Tool integration completed: %d registered, %d failed, %d skipped", registered_count, failed_count, skipped_count)

        except Exception as e:
            result.status = IntegrationStatus.FAILED
            result.error_message = str(e)
            result.completed_at = time.time()
            logger.error("Tool integration failed: %s", e, exc_info=True)

        self._last_sync_time = time.time()
        return result

    def _get_all_tools(self) -> dict[str, Any]:
        """获取所有已注册的工具"""
        tools = {}

        try:
            # 尝试从工具注册表获取
            from deerflow.tools import get_all_tools

            all_tools = get_all_tools()
            for name, tool in all_tools.items():
                tools[name] = {
                    "name": name,
                    "description": getattr(tool, "description", f"Tool: {name}"),
                    "tool_obj": tool,
                }
        except ImportError:
            logger.debug("deerflow.tools.get_all_tools not available, using builtin tools")
        except Exception as e:
            logger.debug("Failed to get tools from registry: %s", e)

        # 获取内置工具
        try:
            from deerflow.tools.builtins import BUILTIN_TOOLS

            for name, tool in BUILTIN_TOOLS.items():
                if name not in tools:
                    tools[name] = {
                        "name": name,
                        "description": getattr(tool, "description", f"Builtin tool: {name}"),
                        "tool_obj": tool,
                        "is_builtin": True,
                    }
        except ImportError:
            logger.debug("BUILTIN_TOOLS not available")
        except Exception as e:
            logger.debug("Failed to get builtin tools: %s", e)

        return tools

    def _convert_to_metadata(self, name: str, tool_info: dict[str, Any]) -> CapabilityMetadata:
        """
        将工具配置转换为CapabilityMetadata

        Args:
            name: 工具名称
            tool_info: 工具信息

        Returns:
            CapabilityMetadata
        """
        description = tool_info.get("description", f"Tool: {name}")
        is_builtin = tool_info.get("is_builtin", False)
        tool_obj = tool_info.get("tool_obj")

        # 推断业务域
        domain = self._infer_domain(name, description)

        # 推断标签
        tags = self._infer_tags(name, description)

        # 提取输入输出schema（如果有）
        input_schema = None
        output_schema = None
        if tool_obj:
            input_schema = getattr(tool_obj, "args_schema", None)
            if hasattr(input_schema, "schema"):
                try:
                    input_schema = input_schema.schema()
                except Exception:
                    pass

        # 构建元数据
        metadata = CapabilityMetadata(
            name=name,
            type=CapabilityType.TOOL,
            description=description,
            version="1.0.0",
            domain=domain,
            tags=tags,
            categories=["tool"],
            input_schema=input_schema,
            output_schema=output_schema,
            status="active",
            is_builtin=is_builtin,
            metadata={
                "source": "tool_registry",
                "tool_type": type(tool_obj).__name__ if tool_obj else "unknown",
            },
        )

        return metadata

    def _infer_domain(self, name: str, description: str) -> str:
        """推断业务域"""
        name_lower = name.lower()
        desc_lower = description.lower()

        # 内容创作工具
        content_keywords = ["generate", "create", "script", "video", "image", "audio", "music", "text", "创作", "生成", "剧本", "视频", "图像", "音乐"]
        if any(k in name_lower or k in desc_lower for k in content_keywords):
            return "content_creation"

        # 商城交易工具
        marketplace_keywords = ["payment", "order", "product", "refund", "shop", "支付", "订单", "商品", "退款", "商城"]
        if any(k in name_lower or k in desc_lower for k in marketplace_keywords):
            return "marketplace"

        # 数据工具
        data_keywords = ["data", "analytics", "search", "query", "database", "数据", "分析", "搜索", "查询", "数据库"]
        if any(k in name_lower or k in desc_lower for k in data_keywords):
            return "data"

        # 系统工具
        system_keywords = ["bash", "shell", "file", "system", "command", "系统", "文件", "命令", "终端"]
        if any(k in name_lower or k in desc_lower for k in system_keywords):
            return "system"

        return "general"

    def _infer_tags(self, name: str, description: str) -> list[str]:
        """推断标签"""
        tags = []

        name_lower = name.lower()
        if "bash" in name_lower or "shell" in name_lower:
            tags.append("shell")
        if "file" in name_lower:
            tags.append("file")
        if "search" in name_lower:
            tags.append("search")
        if "generate" in name_lower:
            tags.append("generation")

        # 去重
        return list(set(tags))[:10]

    def get_registered_tools(self) -> set[str]:
        """获取已注册的工具集合"""
        return set(self._registered_tools)

    @property
    def last_sync_time(self) -> float | None:
        """获取最后同步时间"""
        return self._last_sync_time
