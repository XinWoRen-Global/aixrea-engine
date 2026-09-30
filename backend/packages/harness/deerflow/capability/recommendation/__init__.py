"""
能力推荐模块（Capability Recommendation）
=========================================

负责能力推荐功能的落地，包括：
1. 能力推荐服务（CapabilityRecommendationService）
2. 能力依赖图谱（CapabilityDependencyGraph）
3. 推荐API接口
4. 与Agent创建流程集成
5. 与任务执行流程集成

核心功能：
- Agent创建时自动推荐可复用的工具、Skill、模型
- 任务执行时自动发现匹配能力
- 能力依赖图谱分析和推荐
- 能力组合推荐
- 个性化推荐（基于用户历史使用）
"""

from deerflow.capability.recommendation.api import (
    create_recommendation_router,
)
from deerflow.capability.recommendation.dependency_graph import (
    CapabilityDependencyGraph,
    DependencyEdge,
    DependencyType,
)
from deerflow.capability.recommendation.service import (
    CapabilityRecommendationService,
    RecommendationContext,
    RecommendationResult,
)

__all__ = [
    # 推荐服务
    "CapabilityRecommendationService",
    "RecommendationContext",
    "RecommendationResult",
    # 依赖图谱
    "CapabilityDependencyGraph",
    "DependencyEdge",
    "DependencyType",
    # API
    "create_recommendation_router",
]
