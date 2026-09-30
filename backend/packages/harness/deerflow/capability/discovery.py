"""
能力发现与推荐引擎（Capability Discovery & Recommendation）
============================================================

负责在新Agent创建或任务执行时，自动发现和推荐可复用的能力。

核心功能：
1. 基于任务描述的能力匹配
2. 基于业务域的能力推荐
3. 基于使用统计的热门能力推荐
4. 基于依赖关系的能力组合推荐
5. 能力兼容性检查
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Any

from deerflow.capability.registry import (
    CapabilityMetadata,
    CapabilityRegistry,
    CapabilityType,
    get_global_registry,
)

logger = logging.getLogger(__name__)


class RecommendationReason(Enum):
    """推荐原因枚举"""

    TASK_MATCH = "task_match"  # 任务匹配
    DOMAIN_MATCH = "domain_match"  # 业务域匹配
    POPULAR = "popular"  # 热门能力
    DEPENDENCY = "dependency"  # 依赖关系
    COMPLEMENTARY = "complementary"  # 互补能力
    SIMILAR = "similar"  # 相似能力


@dataclass
class CapabilityRecommendation:
    """能力推荐结果"""

    capability: CapabilityMetadata
    score: float  # 推荐分数 0-1
    reasons: list[RecommendationReason] = field(default_factory=list)
    reason_details: list[str] = field(default_factory=list)
    compatibility_score: float = 1.0  # 兼容性分数

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability": self.capability.to_dict(),
            "score": self.score,
            "reasons": [r.value for r in self.reasons],
            "reason_details": self.reason_details,
            "compatibility_score": self.compatibility_score,
        }


class CapabilityDiscovery:
    """
    能力发现与推荐引擎

    基于任务描述、业务域、使用统计等多维度，
    自动发现和推荐可复用的能力。
    """

    _KEYWORD_CACHE_MAX_SIZE = 1000  # 防止缓存无限增长

    def __init__(self, registry: CapabilityRegistry | None = None):
        self.registry = registry or get_global_registry()
        self._task_keywords_cache: dict[str, list[str]] = {}
        self._keyword_cache_lock = Lock()

    def recommend_for_task(self, task_description: str, domain: str | None = None, capability_types: list[CapabilityType] | None = None, max_results: int = 10, min_score: float = 0.3) -> list[CapabilityRecommendation]:
        """
        基于任务描述推荐能力

        Args:
            task_description: 任务描述
            domain: 业务域（可选）
            capability_types: 能力类型过滤（可选）
            max_results: 最大结果数
            min_score: 最低分数

        Returns:
            推荐的能力列表
        """
        # 提取任务关键词
        keywords = self._extract_keywords(task_description)

        # 获取候选能力
        candidates = self.registry.get_all()

        # 按类型过滤
        if capability_types:
            candidates = [c for c in candidates if c.type in capability_types]

        # 按业务域过滤并加分
        if domain:
            domain_candidates = [c for c in candidates if c.domain == domain]
            other_candidates = [c for c in candidates if c.domain != domain]
        else:
            domain_candidates = []
            other_candidates = candidates

        # 计算推荐分数
        recommendations = []

        for capability in domain_candidates:
            score, reasons, details = self._calculate_match_score(capability, keywords, task_description)
            # 业务域匹配加分
            score = min(1.0, score + 0.2)
            if RecommendationReason.DOMAIN_MATCH not in reasons:
                reasons.append(RecommendationReason.DOMAIN_MATCH)
                details.append(f"业务域匹配: {domain}")

            if score >= min_score:
                recommendations.append(
                    CapabilityRecommendation(
                        capability=capability,
                        score=score,
                        reasons=reasons,
                        reason_details=details,
                    )
                )

        for capability in other_candidates:
            score, reasons, details = self._calculate_match_score(capability, keywords, task_description)

            if score >= min_score:
                recommendations.append(
                    CapabilityRecommendation(
                        capability=capability,
                        score=score,
                        reasons=reasons,
                        reason_details=details,
                    )
                )

        # 按分数排序
        recommendations.sort(key=lambda r: r.score, reverse=True)

        return recommendations[:max_results]

    def recommend_for_agent(self, agent_name: str, agent_domain: str, existing_capabilities: list[str], max_results: int = 10) -> list[CapabilityRecommendation]:
        """
        为Agent推荐可复用的能力

        Args:
            agent_name: Agent名称
            agent_domain: Agent业务域
            existing_capabilities: 已有的能力名称列表
            max_results: 最大结果数

        Returns:
            推荐的能力列表
        """
        # 获取同业务域的能力
        domain_capabilities = self.registry.list_by_domain(agent_domain)

        # 过滤已有的能力
        new_capabilities = [c for c in domain_capabilities if c.name not in existing_capabilities]

        # 按热门程度排序（这里简化为按创建时间，实际应该按使用统计）
        new_capabilities.sort(key=lambda c: c.updated_at, reverse=True)

        recommendations = []
        for capability in new_capabilities[:max_results]:
            recommendations.append(
                CapabilityRecommendation(
                    capability=capability,
                    score=0.7,  # 基础分数
                    reasons=[RecommendationReason.DOMAIN_MATCH, RecommendationReason.POPULAR],
                    reason_details=[f"同业务域能力: {agent_domain}", "热门能力推荐"],
                )
            )

        return recommendations

    def find_complementary_capabilities(self, capability_name: str, capability_type: CapabilityType, max_results: int = 5) -> list[CapabilityRecommendation]:
        """
        查找互补能力

        Args:
            capability_name: 能力名称
            capability_type: 能力类型
            max_results: 最大结果数

        Returns:
            互补能力列表
        """
        capability = self.registry.get(capability_name, capability_type)
        if not capability:
            return []

        # 查找同业务域的其他类型能力
        domain_capabilities = self.registry.list_by_domain(capability.domain)
        complementary = [c for c in domain_capabilities if c.type != capability_type and c.name != capability_name]

        recommendations = []
        for comp in complementary[:max_results]:
            recommendations.append(
                CapabilityRecommendation(
                    capability=comp,
                    score=0.6,
                    reasons=[RecommendationReason.COMPLEMENTARY, RecommendationReason.DOMAIN_MATCH],
                    reason_details=[f"与 {capability_name} 互补", f"同业务域: {capability.domain}"],
                )
            )

        return recommendations

    def check_compatibility(self, capability1: CapabilityMetadata, capability2: CapabilityMetadata) -> tuple[bool, float, list[str]]:
        """
        检查两个能力的兼容性

        Args:
            capability1: 能力1
            capability2: 能力2

        Returns:
            (是否兼容, 兼容性分数, 不兼容原因列表)
        """
        issues = []
        score = 1.0

        # 检查业务域一致性
        if capability1.domain != capability2.domain:
            score -= 0.2
            issues.append(f"业务域不同: {capability1.domain} vs {capability2.domain}")

        # 检查权限冲突
        permission_conflicts = set(capability1.required_permissions) & set(capability2.required_permissions)
        if permission_conflicts:
            score -= 0.1
            issues.append(f"权限重叠: {permission_conflicts}")

        # 检查状态
        if capability1.status == "deprecated" or capability2.status == "deprecated":
            score -= 0.3
            issues.append("包含已弃用能力")

        return score > 0.5, max(0.0, score), issues

    def _extract_keywords(self, text: str) -> list[str]:
        """从文本中提取关键词（线程安全，带 LRU 风格缓存）"""
        # 检查缓存（读操作不需要锁）
        cached = self._task_keywords_cache.get(text)
        if cached is not None:
            return cached

        # 简单的关键词提取：按空格和标点分割，过滤停用词
        stop_words = {
            "的",
            "了",
            "在",
            "是",
            "我",
            "有",
            "和",
            "就",
            "不",
            "人",
            "都",
            "一",
            "一个",
            "上",
            "也",
            "很",
            "到",
            "说",
            "要",
            "去",
            "你",
            "会",
            "着",
            "没有",
            "看",
            "好",
            "自己",
            "这",
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "must",
            "can",
            "need",
            "dare",
            "ought",
            "used",
            "to",
            "of",
            "in",
            "for",
            "on",
            "with",
            "at",
            "by",
            "from",
            "as",
            "into",
            "through",
            "during",
            "before",
            "after",
            "above",
            "below",
            "between",
            "out",
            "off",
            "over",
            "under",
            "again",
            "further",
            "then",
            "once",
        }

        # 简单分词
        words = text.lower().replace(",", " ").replace(".", " ").replace("，", " ").replace("。", " ").split()
        keywords = list(set(w for w in words if w not in stop_words and len(w) > 1))

        # 写缓存（需要锁）
        with self._keyword_cache_lock:
            self._task_keywords_cache[text] = keywords
            # 防止缓存无限增长
            if len(self._task_keywords_cache) > self._KEYWORD_CACHE_MAX_SIZE:
                # 淘汰最旧的一半
                keys_to_remove = len(self._task_keywords_cache) - self._KEYWORD_CACHE_MAX_SIZE // 2
                for old_key in list(self._task_keywords_cache.keys())[:keys_to_remove]:
                    self._task_keywords_cache.pop(old_key, None)

        return keywords

    def _calculate_match_score(self, capability: CapabilityMetadata, keywords: list[str], task_description: str) -> tuple[float, list[RecommendationReason], list[str]]:
        """计算能力与任务的匹配分数"""
        score = 0.0
        reasons = []
        details = []

        # 关键词匹配
        capability_text = f"{capability.name} {capability.description} {' '.join(capability.tags)}".lower()
        matched_keywords = [k for k in keywords if k in capability_text]

        if matched_keywords:
            keyword_score = min(1.0, len(matched_keywords) / max(1, len(keywords)) * 1.5)
            score += keyword_score * 0.6
            reasons.append(RecommendationReason.TASK_MATCH)
            details.append(f"关键词匹配: {matched_keywords[:5]}")

        # 描述相似度（简化版）
        if any(k in capability.description.lower() for k in keywords):
            score += 0.2
            details.append("描述匹配")

        # 热门能力加分（简化版，实际应该按使用统计）
        if capability.status == "active" and capability.is_builtin:
            score += 0.1
            reasons.append(RecommendationReason.POPULAR)
            details.append("内置热门能力")

        return min(1.0, score), reasons, details
