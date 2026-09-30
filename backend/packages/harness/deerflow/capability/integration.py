"""
能力注册中心集成示例
====================

展示如何使用统一能力注册中心进行能力注册、发现、推荐和统计。

使用场景：
1. 系统启动时注册所有内置能力
2. 新Agent创建时推荐可复用能力
3. 任务执行时自动发现匹配能力
4. 运行时统计能力使用情况
5. 能力版本管理和灰度发布
"""

import logging

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
    get_global_usage_tracker,
)
from deerflow.capability.version import (
    CapabilityVersionManager,
    get_global_version_manager,
)

logger = logging.getLogger(__name__)


class CapabilityPlatform:
    """
    能力平台集成类

    整合注册中心、发现引擎、版本管理器、使用统计器，
    提供统一的能力管理接口。
    """

    def __init__(self, registry: CapabilityRegistry | None = None, discovery: CapabilityDiscovery | None = None, version_manager: CapabilityVersionManager | None = None, usage_tracker: CapabilityUsageTracker | None = None):
        self.registry = registry or get_global_registry()
        self.discovery = discovery or CapabilityDiscovery(self.registry)
        self.version_manager = version_manager or get_global_version_manager()
        self.usage_tracker = usage_tracker or get_global_usage_tracker()

    def register_capability(self, metadata: CapabilityMetadata) -> bool:
        """注册能力"""
        return self.registry.register(metadata)

    def recommend_for_task(self, task_description: str, domain: str | None = None, capability_types: list[CapabilityType] | None = None, max_results: int = 10) -> list[CapabilityRecommendation]:
        """为任务推荐能力"""
        return self.discovery.recommend_for_task(task_description, domain, capability_types, max_results)

    def record_usage(self, usage: CapabilityUsage):
        """记录能力使用情况"""
        self.usage_tracker.record_usage(usage)

    def get_top_capabilities(self, type: CapabilityType | None = None, limit: int = 10) -> list:
        """获取热门能力"""
        return self.usage_tracker.get_top_capabilities(type, limit)

    def get_platform_statistics(self) -> dict:
        """获取平台统计信息"""
        return {
            "registry": self.registry.get_statistics(),
            "usage": self.usage_tracker.get_statistics_summary(),
        }


# ============================================================================
# 内置能力注册示例
# ============================================================================


def register_builtin_capabilities(registry: CapabilityRegistry | None = None):
    """
    注册内置能力

    在系统启动时调用，注册所有内置的Agent、工具、Skill、模型。
    """
    registry = registry or get_global_registry()

    # 内容创作域能力
    content_creation_capabilities = [
        CapabilityMetadata(
            name="drama-agent",
            type=CapabilityType.AGENT,
            description="短剧创作Agent，负责剧本生成、分镜设计、视频生成全流程",
            domain="content_creation",
            tags=["短剧", "视频", "剧本", "分镜"],
            categories=["content", "video"],
            is_builtin=True,
        ),
        CapabilityMetadata(
            name="novel-agent",
            type=CapabilityType.AGENT,
            description="小说创作Agent，负责大纲生成、章节创作、质量检查",
            domain="content_creation",
            tags=["小说", "文本", "大纲", "章节"],
            categories=["content", "text"],
            is_builtin=True,
        ),
        CapabilityMetadata(
            name="comic-agent",
            type=CapabilityType.AGENT,
            description="漫画创作Agent，负责分镜设计、角色设计、画面生成",
            domain="content_creation",
            tags=["漫画", "图像", "分镜", "角色"],
            categories=["content", "image"],
            is_builtin=True,
        ),
        CapabilityMetadata(
            name="music-agent",
            type=CapabilityType.AGENT,
            description="音乐创作Agent，负责歌词生成、旋律生成、编曲制作",
            domain="content_creation",
            tags=["音乐", "音频", "歌词", "编曲"],
            categories=["content", "audio"],
            is_builtin=True,
        ),
        CapabilityMetadata(
            name="interactive-agent",
            type=CapabilityType.AGENT,
            description="互动内容创作Agent，负责分支设计、剧情生成、逻辑验证",
            domain="content_creation",
            tags=["互动", "游戏", "分支", "剧情"],
            categories=["content", "interactive"],
            is_builtin=True,
        ),
    ]

    # 商城交易域能力
    marketplace_capabilities = [
        CapabilityMetadata(
            name="product-manager",
            type=CapabilityType.AGENT,
            description="商品管理Agent，负责商品上架、审核、定价、库存管理",
            domain="marketplace",
            tags=["商品", "商城", "定价", "库存"],
            categories=["marketplace", "product"],
            is_builtin=True,
        ),
        CapabilityMetadata(
            name="order-processor",
            type=CapabilityType.AGENT,
            description="订单处理Agent，负责订单创建、确认、履约、跟踪",
            domain="marketplace",
            tags=["订单", "交易", "履约", "跟踪"],
            categories=["marketplace", "order"],
            is_builtin=True,
        ),
        CapabilityMetadata(
            name="payment-settlement",
            type=CapabilityType.AGENT,
            description="支付结算Agent，负责支付通道管理、对账结算、分润计算",
            domain="marketplace",
            tags=["支付", "结算", "对账", "分润"],
            categories=["marketplace", "payment"],
            is_builtin=True,
        ),
        CapabilityMetadata(
            name="refund-service",
            type=CapabilityType.AGENT,
            description="退款售后Agent，负责退款审核、退款处理、纠纷处理",
            domain="marketplace",
            tags=["退款", "售后", "纠纷", "客服"],
            categories=["marketplace", "refund"],
            is_builtin=True,
        ),
    ]

    # 用户增长域能力
    growth_capabilities = [
        CapabilityMetadata(
            name="user-growth",
            type=CapabilityType.AGENT,
            description="用户增长Agent，负责用户获取、激活、留存、转化、推荐",
            domain="growth",
            tags=["用户", "增长", "获客", "留存", "推荐"],
            categories=["growth", "user"],
            is_builtin=True,
        ),
    ]

    # 分发运营域能力
    distribution_capabilities = [
        CapabilityMetadata(
            name="distribution-ops",
            type=CapabilityType.AGENT,
            description="分发运营Agent，负责多平台内容分发、内容运营、活动策划",
            domain="distribution",
            tags=["分发", "运营", "多平台", "活动"],
            categories=["distribution", "ops"],
            is_builtin=True,
        ),
    ]

    # 客服支持域能力
    support_capabilities = [
        CapabilityMetadata(
            name="customer-support",
            type=CapabilityType.AGENT,
            description="客服支持Agent，负责智能客服、工单处理、知识库管理",
            domain="support",
            tags=["客服", "工单", "知识库", "支持"],
            categories=["support", "customer"],
            is_builtin=True,
        ),
    ]

    # 数据智能域能力
    data_capabilities = [
        CapabilityMetadata(
            name="data-intelligence",
            type=CapabilityType.AGENT,
            description="数据智能Agent，负责数据采集、分析、报表、预测、推荐",
            domain="data",
            tags=["数据", "分析", "报表", "预测", "智能"],
            categories=["data", "intelligence"],
            is_builtin=True,
        ),
    ]

    # 注册所有能力
    all_capabilities = content_creation_capabilities + marketplace_capabilities + growth_capabilities + distribution_capabilities + support_capabilities + data_capabilities

    registered_count = 0
    for capability in all_capabilities:
        if registry.register(capability):
            registered_count += 1

    logger.info("Registered %d builtin capabilities", registered_count)
    return registered_count


# ============================================================================
# 使用示例
# ============================================================================


def example_usage():
    """使用示例"""

    # 1. 初始化能力平台
    platform = CapabilityPlatform()

    # 2. 注册内置能力
    register_builtin_capabilities(platform.registry)

    # 3. 为任务推荐能力
    task = "创作一部关于都市修仙的短剧，需要剧本生成和视频制作"
    recommendations = platform.recommend_for_task(
        task_description=task,
        domain="content_creation",
        max_results=5,
    )

    print("推荐的能力:")
    for rec in recommendations:
        print(f"  - {rec.capability.name}: {rec.score:.2f} ({rec.capability.description})")

    # 4. 记录能力使用情况
    usage = CapabilityUsage(
        capability_name="drama-agent",
        capability_type=CapabilityType.AGENT,
        timestamp=__import__("time").time(),
        success=True,
        latency_ms=1500.5,
        cost=0.05,
        domain="content_creation",
    )
    platform.record_usage(usage)

    # 5. 获取热门能力
    top_capabilities = platform.get_top_capabilities(limit=5)
    print("\n热门能力:")
    for key, metrics in top_capabilities:
        print(f"  - {key}: {metrics.total_calls} calls, {metrics.success_rate:.2%} success")

    # 6. 获取平台统计
    stats = platform.get_platform_statistics()
    print(f"\n平台统计: {stats}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    example_usage()
