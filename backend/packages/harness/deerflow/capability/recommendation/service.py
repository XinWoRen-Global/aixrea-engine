"""
能力推荐服务（Capability Recommendation Service）
==================================================

负责能力推荐的核心逻辑，包括：
1. Agent创建时推荐可复用的工具、Skill、模型
2. 任务执行时推荐匹配能力
3. 基于业务域的推荐
4. 基于使用历史的个性化推荐
5. 能力组合推荐
"""

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

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
    CapabilityUsageTracker,
    get_global_usage_tracker,
)

logger = logging.getLogger(__name__)


@dataclass
class RecommendationContext:
    """推荐上下文"""

    # 场景类型
    scenario: str  # "agent_creation", "task_execution", "capability_combo"

    # 业务域
    domain: str | None = None

    # 任务描述（用于语义匹配）
    task_description: str | None = None

    # Agent信息（Agent创建场景）
    agent_name: str | None = None
    agent_description: str | None = None

    # 已有的能力（避免重复推荐）
    existing_capabilities: list[str] = field(default_factory=list)

    # 用户ID（个性化推荐）
    user_id: str | None = None

    # 推荐的能力类型过滤
    capability_types: list[CapabilityType] | None = None

    # 最大推荐数量
    max_results: int = 10

    # 最低推荐分数
    min_score: float = 0.3

    # 扩展参数
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RecommendationResult:
    """推荐结果"""

    context: RecommendationContext
    recommendations: list[CapabilityRecommendation] = field(default_factory=list)
    generated_at: float = field(default_factory=time.time)

    # 推荐统计
    total_candidates: int = 0
    filtered_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.context.scenario,
            "domain": self.context.domain,
            "recommendations": [r.to_dict() for r in self.recommendations],
            "total_candidates": self.total_candidates,
            "filtered_count": self.filtered_count,
            "generated_at": self.generated_at,
        }


class CapabilityRecommendationService:
    """
    能力推荐服务

    负责能力推荐的核心逻辑，提供多种推荐策略。
    """

    def __init__(self, registry: CapabilityRegistry | None = None, discovery: CapabilityDiscovery | None = None, usage_tracker: CapabilityUsageTracker | None = None):
        self.registry = registry or get_global_registry()
        self.discovery = discovery or CapabilityDiscovery(self.registry)
        self.usage_tracker = usage_tracker or get_global_usage_tracker()

        # 能力组合规则（预定义的常用能力组合）
        self._combo_rules: dict[str, list[str]] = self._init_combo_rules()

        # 用户使用历史（简化版，实际应该持久化）
        self._user_usage_history: dict[str, list[str]] = defaultdict(list)

    def recommend_for_agent_creation(self, agent_name: str, agent_description: str, domain: str | None = None, existing_capabilities: list[str] | None = None, user_id: str | None = None, max_results: int = 10) -> RecommendationResult:
        """
        Agent创建时推荐可复用的能力

        Args:
            agent_name: Agent名称
            agent_description: Agent描述
            domain: 业务域
            existing_capabilities: 已有的能力列表
            user_id: 用户ID
            max_results: 最大推荐数量

        Returns:
            推荐结果
        """
        context = RecommendationContext(
            scenario="agent_creation",
            domain=domain,
            task_description=f"{agent_name} {agent_description}",
            agent_name=agent_name,
            agent_description=agent_description,
            existing_capabilities=existing_capabilities or [],
            user_id=user_id,
            max_results=max_results,
        )

        return self._generate_recommendations(context)

    def recommend_for_task_execution(self, task_description: str, domain: str | None = None, available_capabilities: list[str] | None = None, user_id: str | None = None, max_results: int = 5) -> RecommendationResult:
        """
        任务执行时推荐匹配能力

        Args:
            task_description: 任务描述
            domain: 业务域
            available_capabilities: 可用的能力列表
            user_id: 用户ID
            max_results: 最大推荐数量

        Returns:
            推荐结果
        """
        context = RecommendationContext(
            scenario="task_execution",
            domain=domain,
            task_description=task_description,
            existing_capabilities=available_capabilities or [],
            user_id=user_id,
            max_results=max_results,
        )

        return self._generate_recommendations(context)

    def recommend_capability_combo(self, capability_name: str, capability_type: CapabilityType, domain: str | None = None, max_results: int = 5) -> RecommendationResult:
        """
        推荐能力组合（与指定能力配合使用的其他能力）

        Args:
            capability_name: 能力名称
            capability_type: 能力类型
            domain: 业务域
            max_results: 最大推荐数量

        Returns:
            推荐结果
        """
        # 获取指定能力的信息
        capability = self.registry.get(capability_name, capability_type)
        if not capability:
            return RecommendationResult(
                context=RecommendationContext(
                    scenario="capability_combo",
                    domain=domain,
                    max_results=max_results,
                )
            )

        context = RecommendationContext(
            scenario="capability_combo",
            domain=domain or capability.domain,
            task_description=capability.description,
            existing_capabilities=[capability_name],
            max_results=max_results,
        )

        # 先查找预定义的组合规则
        combo_recommendations = []
        if capability_name in self._combo_rules:
            for combo_name in self._combo_rules[capability_name]:
                # 查找组合中的能力
                for ctype in CapabilityType:
                    combo_cap = self.registry.get(combo_name, ctype)
                    if combo_cap:
                        combo_recommendations.append(
                            CapabilityRecommendation(
                                capability=combo_cap,
                                score=0.9,
                                reasons=[],
                                reason_details=[f"预定义组合: {capability_name} + {combo_name}"],
                            )
                        )
                        break

        # 再使用发现引擎推荐互补能力
        complementary = self.discovery.find_complementary_capabilities(capability_name, capability_type, max_results)

        # 合并推荐结果
        all_recommendations = combo_recommendations + complementary

        # 去重和排序
        seen = set()
        unique_recommendations = []
        for rec in all_recommendations:
            if rec.capability.name not in seen:
                seen.add(rec.capability.name)
                unique_recommendations.append(rec)

        unique_recommendations.sort(key=lambda r: r.score, reverse=True)

        result = RecommendationResult(
            context=context,
            recommendations=unique_recommendations[:max_results],
            total_candidates=len(all_recommendations),
        )

        return result

    def get_personalized_recommendations(self, user_id: str, domain: str | None = None, max_results: int = 10) -> RecommendationResult:
        """
        基于用户历史的个性化推荐

        Args:
            user_id: 用户ID
            domain: 业务域
            max_results: 最大推荐数量

        Returns:
            推荐结果
        """
        # 获取用户使用历史
        user_history = self._user_usage_history.get(user_id, [])

        # 基于用户常用的能力，推荐相似的能力
        if not user_history:
            # 新用户，推荐热门能力
            return self._recommend_popular(domain, max_results)

        # 获取用户最近使用的能力
        recent_capabilities = user_history[-10:] if len(user_history) > 10 else user_history

        # 基于这些能力推荐相似能力
        all_recommendations = []
        for cap_name in recent_capabilities:
            for ctype in CapabilityType:
                cap = self.registry.get(cap_name, ctype)
                if cap:
                    similar = self.discovery.find_complementary_capabilities(cap_name, ctype, max_results=3)
                    all_recommendations.extend(similar)
                    break

        # 去重和排序
        seen = set(user_history)  # 排除已使用的
        unique_recommendations = []
        for rec in all_recommendations:
            if rec.capability.name not in seen:
                seen.add(rec.capability.name)
                unique_recommendations.append(rec)

        unique_recommendations.sort(key=lambda r: r.score, reverse=True)

        context = RecommendationContext(
            scenario="personalized",
            domain=domain,
            user_id=user_id,
            max_results=max_results,
        )

        return RecommendationResult(
            context=context,
            recommendations=unique_recommendations[:max_results],
            total_candidates=len(all_recommendations),
        )

    def record_usage(self, user_id: str, capability_name: str):
        """记录用户使用历史（用于个性化推荐）"""
        self._user_usage_history[user_id].append(capability_name)
        # 只保留最近100条
        if len(self._user_usage_history[user_id]) > 100:
            self._user_usage_history[user_id] = self._user_usage_history[user_id][-100:]

    def _generate_recommendations(self, context: RecommendationContext) -> RecommendationResult:
        """生成推荐结果（核心逻辑）"""
        all_recommendations = []

        # 策略1：基于任务描述的语义匹配
        if context.task_description:
            task_recommendations = self.discovery.recommend_for_task(
                task_description=context.task_description,
                domain=context.domain,
                capability_types=context.capability_types,
                max_results=context.max_results * 2,
                min_score=context.min_score,
            )
            all_recommendations.extend(task_recommendations)

        # 策略2：基于业务域的推荐
        if context.domain:
            domain_capabilities = self.registry.list_by_domain(context.domain)
            for cap in domain_capabilities:
                # 检查是否已在推荐列表中
                if any(r.capability.name == cap.name for r in all_recommendations):
                    continue

                # 检查是否已存在
                if cap.name in context.existing_capabilities:
                    continue

                # 检查类型过滤
                if context.capability_types and cap.type not in context.capability_types:
                    continue

                all_recommendations.append(
                    CapabilityRecommendation(
                        capability=cap,
                        score=0.6,
                        reasons=[],
                        reason_details=[f"同业务域能力: {context.domain}"],
                    )
                )

        # 策略3：热门能力推荐
        popular = self._get_popular_capabilities(context.domain, context.max_results)
        for cap in popular:
            if any(r.capability.name == cap.name for r in all_recommendations):
                continue
            if cap.name in context.existing_capabilities:
                continue
            if context.capability_types and cap.type not in context.capability_types:
                continue

            all_recommendations.append(
                CapabilityRecommendation(
                    capability=cap,
                    score=0.5,
                    reasons=[],
                    reason_details=["热门能力推荐"],
                )
            )

        # 策略4：个性化推荐（如果有user_id）
        if context.user_id:
            personalized = self.get_personalized_recommendations(context.user_id, context.domain, context.max_results)
            for rec in personalized.recommendations:
                if any(r.capability.name == rec.capability.name for r in all_recommendations):
                    continue
                if rec.capability.name in context.existing_capabilities:
                    continue
                all_recommendations.append(rec)

        # 过滤已有的能力
        filtered = [r for r in all_recommendations if r.capability.name not in context.existing_capabilities]

        # 按分数排序
        filtered.sort(key=lambda r: r.score, reverse=True)

        return RecommendationResult(
            context=context,
            recommendations=filtered[: context.max_results],
            total_candidates=len(all_recommendations),
            filtered_count=len(all_recommendations) - len(filtered),
        )

    def _get_popular_capabilities(self, domain: str | None = None, limit: int = 10) -> list[CapabilityMetadata]:
        """获取热门能力（基于使用统计）"""
        # 从使用统计器获取热门能力
        top_capabilities = self.usage_tracker.get_top_capabilities(limit=limit * 2)

        result = []
        for key, metrics in top_capabilities:
            # 解析key (type:name)
            parts = key.split(":", 1)
            if len(parts) != 2:
                continue

            type_str, name = parts
            try:
                cap_type = CapabilityType(type_str)
            except ValueError:
                continue

            cap = self.registry.get(name, cap_type)
            if cap:
                if domain and cap.domain != domain:
                    continue
                result.append(cap)

                if len(result) >= limit:
                    break

        # 如果没有统计数据，返回所有活跃能力
        if not result:
            all_caps = self.registry.get_all()
            result = [c for c in all_caps if c.status == "active"][:limit]

        return result

    def _recommend_popular(self, domain: str | None, max_results: int) -> RecommendationResult:
        """推荐热门能力（新用户）"""
        popular = self._get_popular_capabilities(domain, max_results)

        recommendations = [
            CapabilityRecommendation(
                capability=cap,
                score=0.5,
                reasons=[],
                reason_details=["热门能力推荐"],
            )
            for cap in popular
        ]

        context = RecommendationContext(
            scenario="popular",
            domain=domain,
            max_results=max_results,
        )

        return RecommendationResult(
            context=context,
            recommendations=recommendations,
            total_candidates=len(popular),
        )

    def _init_combo_rules(self) -> dict[str, list[str]]:
        """初始化预定义的能力组合规则"""
        return {
            # 短剧创作组合
            "drama-agent": ["video-generation-tool", "subtitle-generation-skill", "music-agent"],
            "drama-executor": ["drama-producer", "quality-inspector-skill"],
            # 小说创作组合
            "novel-agent": ["text-generation-tool", "character-consistency-skill"],
            "novel-executor": ["novel-producer", "quality-inspector-skill"],
            # 漫画创作组合
            "comic-agent": ["image-generation-tool", "character-design-skill"],
            "comics-executor": ["comic-producer", "quality-inspector-skill"],
            # 音乐创作组合
            "music-agent": ["audio-generation-tool", "lyric-writing-skill"],
            "music-executor": ["music-producer", "quality-inspector-skill"],
            # 商城交易组合
            "product-manager": ["order-processor", "payment-settlement"],
            "order-processor": ["payment-settlement", "refund-service"],
            "payment-settlement": ["refund-service", "data-intelligence"],
            # 用户增长组合
            "user-growth": ["data-intelligence", "distribution-ops"],
            # 分发运营组合
            "distribution-ops": ["data-intelligence", "customer-support"],
        }


# 全局推荐服务单例
_global_recommendation_service: CapabilityRecommendationService | None = None
_global_recommendation_lock = None


def get_global_recommendation_service() -> CapabilityRecommendationService:
    """获取全局推荐服务单例"""
    global _global_recommendation_service, _global_recommendation_lock
    if _global_recommendation_lock is None:
        from threading import Lock

        _global_recommendation_lock = Lock()

    if _global_recommendation_service is None:
        with _global_recommendation_lock:
            if _global_recommendation_service is None:
                _global_recommendation_service = CapabilityRecommendationService()
    return _global_recommendation_service
