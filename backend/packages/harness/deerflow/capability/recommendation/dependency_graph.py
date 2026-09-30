"""
能力依赖图谱（Capability Dependency Graph）
============================================

负责分析和管理能力间的依赖关系，包括：
1. 能力依赖关系的建立和查询
2. 依赖类型分类（硬依赖、软依赖、互补、相似）
3. 依赖路径分析
4. 依赖环检测
5. 基于依赖图谱的能力推荐
"""

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from deerflow.capability.registry import (
    CapabilityMetadata,
    CapabilityRegistry,
    CapabilityType,
    get_global_registry,
)

logger = logging.getLogger(__name__)


class DependencyType(Enum):
    """依赖类型枚举"""

    HARD = "hard"  # 硬依赖：必须有
    SOFT = "soft"  # 软依赖：推荐有
    COMPLEMENTARY = "complementary"  # 互补：配合使用效果更好
    SIMILAR = "similar"  # 相似：可替代
    COMPOSITE = "composite"  # 组合：组合成更大能力


@dataclass
class DependencyEdge:
    """依赖边"""

    source: str  # 源能力名称
    source_type: CapabilityType
    target: str  # 目标能力名称
    target_type: CapabilityType
    type: DependencyType
    weight: float = 1.0  # 权重 0-1
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "source_type": self.source_type.value,
            "target": self.target,
            "target_type": self.target_type.value,
            "type": self.type.value,
            "weight": self.weight,
            "description": self.description,
        }


class CapabilityDependencyGraph:
    """
    能力依赖图谱

    负责分析和管理能力间的依赖关系。
    """

    def __init__(self, registry: CapabilityRegistry | None = None):
        self.registry = registry or get_global_registry()

        # 邻接表：source -> List[DependencyEdge]
        self._adjacency: dict[str, list[DependencyEdge]] = defaultdict(list)

        # 反向邻接表：target -> List[DependencyEdge]
        self._reverse_adjacency: dict[str, list[DependencyEdge]] = defaultdict(list)

        # 所有边
        self._edges: list[DependencyEdge] = []

        # 节点集合
        self._nodes: set[str] = set()

    def add_dependency(self, source: str, source_type: CapabilityType, target: str, target_type: CapabilityType, dep_type: DependencyType = DependencyType.SOFT, weight: float = 1.0, description: str = "") -> bool:
        """
        添加依赖关系

        Args:
            source: 源能力名称
            source_type: 源能力类型
            target: 目标能力名称
            target_type: 目标能力类型
            dep_type: 依赖类型
            weight: 权重
            description: 描述

        Returns:
            是否添加成功
        """
        # 检查是否已存在
        for edge in self._adjacency.get(source, []):
            if edge.target == target and edge.type == dep_type:
                logger.debug("Dependency already exists: %s -> %s (%s)", source, target, dep_type.value)
                return False

        edge = DependencyEdge(
            source=source,
            source_type=source_type,
            target=target,
            target_type=target_type,
            type=dep_type,
            weight=weight,
            description=description,
        )

        self._adjacency[source].append(edge)
        self._reverse_adjacency[target].append(edge)
        self._edges.append(edge)
        self._nodes.add(source)
        self._nodes.add(target)

        logger.debug("Dependency added: %s -> %s (%s, weight=%.2f)", source, target, dep_type.value, weight)
        return True

    def remove_dependency(self, source: str, target: str, dep_type: DependencyType | None = None) -> bool:
        """
        移除依赖关系

        Args:
            source: 源能力名称
            target: 目标能力名称
            dep_type: 依赖类型（可选，不指定则移除所有）

        Returns:
            是否移除成功
        """
        removed = False

        # 从正向邻接表移除
        if source in self._adjacency:
            original_len = len(self._adjacency[source])
            if dep_type:
                self._adjacency[source] = [e for e in self._adjacency[source] if not (e.target == target and e.type == dep_type)]
            else:
                self._adjacency[source] = [e for e in self._adjacency[source] if e.target != target]
            removed = len(self._adjacency[source]) < original_len

        # 从反向邻接表移除
        if target in self._reverse_adjacency:
            if dep_type:
                self._reverse_adjacency[target] = [e for e in self._reverse_adjacency[target] if not (e.source == source and e.type == dep_type)]
            else:
                self._reverse_adjacency[target] = [e for e in self._reverse_adjacency[target] if e.source != source]

        # 从边列表移除
        if dep_type:
            self._edges = [e for e in self._edges if not (e.source == source and e.target == target and e.type == dep_type)]
        else:
            self._edges = [e for e in self._edges if not (e.source == source and e.target == target)]

        return removed

    def get_dependencies(self, capability_name: str, dep_type: DependencyType | None = None) -> list[DependencyEdge]:
        """
        获取指定能力的依赖（出边）

        Args:
            capability_name: 能力名称
            dep_type: 依赖类型过滤（可选）

        Returns:
            依赖边列表
        """
        edges = self._adjacency.get(capability_name, [])
        if dep_type:
            edges = [e for e in edges if e.type == dep_type]
        return edges

    def get_dependents(self, capability_name: str, dep_type: DependencyType | None = None) -> list[DependencyEdge]:
        """
        获取依赖于指定能力的能力（入边）

        Args:
            capability_name: 能力名称
            dep_type: 依赖类型过滤（可选）

        Returns:
            依赖边列表
        """
        edges = self._reverse_adjacency.get(capability_name, [])
        if dep_type:
            edges = [e for e in edges if e.type == dep_type]
        return edges

    def get_all_dependencies(self, capability_name: str, max_depth: int = 3) -> list[DependencyEdge]:
        """
        获取指定能力的所有传递依赖（BFS）

        Args:
            capability_name: 能力名称
            max_depth: 最大深度

        Returns:
            所有依赖边列表
        """
        visited = set()
        result = []
        queue = deque([(capability_name, 0)])

        while queue:
            current, depth = queue.popleft()

            if depth >= max_depth:
                continue

            for edge in self._adjacency.get(current, []):
                if edge.target not in visited:
                    visited.add(edge.target)
                    result.append(edge)
                    queue.append((edge.target, depth + 1))

        return result

    def detect_cycle(self) -> list[list[str]]:
        """
        检测依赖环

        Returns:
            环列表（每个环是一个能力名称列表）
        """
        cycles = []
        visited = set()
        rec_stack = set()

        def dfs(node: str, path: list[str]):
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for edge in self._adjacency.get(node, []):
                if edge.target not in visited:
                    dfs(edge.target, path)
                elif edge.target in rec_stack:
                    # 找到环
                    cycle_start = path.index(edge.target)
                    cycle = path[cycle_start:] + [edge.target]
                    cycles.append(cycle)

            path.pop()
            rec_stack.remove(node)

        for node in self._nodes:
            if node not in visited:
                dfs(node, [])

        return cycles

    def get_recommendations(self, capability_name: str, capability_type: CapabilityType, dep_types: list[DependencyType] | None = None, max_results: int = 10) -> list[tuple[DependencyEdge, CapabilityMetadata]]:
        """
        基于依赖图谱推荐能力

        Args:
            capability_name: 能力名称
            capability_type: 能力类型
            dep_types: 依赖类型过滤（可选）
            max_results: 最大结果数

        Returns:
            (依赖边, 能力元数据) 列表
        """
        # 获取直接依赖
        direct_deps = self.get_dependencies(capability_name)

        # 获取传递依赖
        transitive_deps = self.get_all_dependencies(capability_name, max_depth=2)

        # 合并
        all_deps = direct_deps + transitive_deps

        # 按类型过滤
        if dep_types:
            all_deps = [e for e in all_deps if e.type in dep_types]

        # 按权重排序
        all_deps.sort(key=lambda e: e.weight, reverse=True)

        # 去重
        seen = set()
        unique_deps = []
        for dep in all_deps:
            if dep.target not in seen:
                seen.add(dep.target)
                unique_deps.append(dep)

        # 获取能力元数据
        result = []
        for dep in unique_deps[:max_results]:
            cap = self.registry.get(dep.target, dep.target_type)
            if cap:
                result.append((dep, cap))

        return result

    def build_from_registry(self):
        """
        从注册中心自动构建依赖图谱

        基于能力的元数据（标签、业务域、描述）自动推断依赖关系。
        """
        all_capabilities = self.registry.get_all()

        # 按业务域分组
        domain_groups: dict[str, list[CapabilityMetadata]] = defaultdict(list)
        for cap in all_capabilities:
            domain_groups[cap.domain].append(cap)

        # 同业务域内的能力建立互补关系
        for domain, caps in domain_groups.items():
            for i, cap1 in enumerate(caps):
                for cap2 in caps[i + 1 :]:
                    # 同业务域、不同类型的能力建立互补关系
                    if cap1.type != cap2.type:
                        self.add_dependency(
                            source=cap1.name,
                            source_type=cap1.type,
                            target=cap2.name,
                            target_type=cap2.type,
                            dep_type=DependencyType.COMPLEMENTARY,
                            weight=0.6,
                            description=f"同业务域({domain})互补能力",
                        )

        # 基于标签的相似性
        tag_groups: dict[str, list[CapabilityMetadata]] = defaultdict(list)
        for cap in all_capabilities:
            for tag in cap.tags:
                tag_groups[tag].append(cap)

        for tag, caps in tag_groups.items():
            if len(caps) < 2:
                continue
            for i, cap1 in enumerate(caps):
                for cap2 in caps[i + 1 :]:
                    if cap1.name != cap2.name and cap1.type == cap2.type:
                        self.add_dependency(
                            source=cap1.name,
                            source_type=cap1.type,
                            target=cap2.name,
                            target_type=cap2.type,
                            dep_type=DependencyType.SIMILAR,
                            weight=0.5,
                            description=f"共享标签({tag})的相似能力",
                        )

        logger.info("Dependency graph built from registry: %d nodes, %d edges", len(self._nodes), len(self._edges))

    def get_statistics(self) -> dict[str, Any]:
        """获取图谱统计信息"""
        type_counts = defaultdict(int)
        for edge in self._edges:
            type_counts[edge.type.value] += 1

        return {
            "total_nodes": len(self._nodes),
            "total_edges": len(self._edges),
            "edges_by_type": dict(type_counts),
            "has_cycle": len(self.detect_cycle()) > 0,
            "cycle_count": len(self.detect_cycle()),
        }

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "nodes": list(self._nodes),
            "edges": [e.to_dict() for e in self._edges],
            "statistics": self.get_statistics(),
        }


# 全局依赖图谱单例
_global_dependency_graph: CapabilityDependencyGraph | None = None
_global_dependency_graph_lock = None


def get_global_dependency_graph() -> CapabilityDependencyGraph:
    """获取全局依赖图谱单例"""
    global _global_dependency_graph, _global_dependency_graph_lock
    if _global_dependency_graph_lock is None:
        from threading import Lock

        _global_dependency_graph_lock = Lock()

    if _global_dependency_graph is None:
        with _global_dependency_graph_lock:
            if _global_dependency_graph is None:
                _global_dependency_graph = CapabilityDependencyGraph()
    return _global_dependency_graph
