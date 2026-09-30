"""
团队长期记忆管理器 — Team Memory Manager

在 DeerFlow 现有 MemoryManager（per-user, per-agent）之上叠加团队级共享记忆层。

核心能力：
  1. 团队 Scope — 记忆按 org_id 分桶，team 级记忆跨 Agent 共享
  2. 四大记忆分类 — code_knowledge / project_docs / conversation_history / working_methods
  3. 自动采集 — Pipeline Executor 执行中自动捕获决策、错误、产出
  4. 按需装配 — 根据 Agent 角色 + 任务语义检索相关记忆，组装为上下文

Scope 模型（三级）：
  ┌──────────┬─────────────────────────────────┐
  │ user_id  │ 个人记忆（偏好、习惯、风格）      │
  │ agent_name│ Agent 专属记忆（领域知识、经验） │
  │ org_id   │ ★团队共享记忆（跨Agent协同）     │
  └──────────┴─────────────────────────────────┘

记忆分类：
  - code_knowledge:      架构决策、技术选型、代码模式、API 设计
  - project_docs:        需求文档、设计规范、PRD、SOP
  - conversation_history: Agent 对话摘要、用户反馈、纠正历史
  - working_methods:     最佳实践、工作流程、避坑指南、经验教训

用法：
  from deerflow.agents.memory.team_memory import TeamMemoryManager

  tm = TeamMemoryManager(memory_manager)
  await tm.capture("pipeline_execution", {
      "category": "working_methods",
      "content": "短剧角色一致性：同剧集所有分镜使用同一 seed，避免角色漂移",
      "agent_name": "drama-executor",
      "org_id": "org_xxx",
  })
  context = await tm.assemble(org_id="org_xxx", agent_role="drama", task="生成12集都市爱情短剧")
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any, Literal

from deerflow.agents.memory.manager import MemoryManager, get_memory_manager

logger = logging.getLogger("team_memory")

# ── 记忆分类 ────────────────────────────────────────────────────────────────

TeamMemoryCategory = Literal[
    "code_knowledge",  # 架构决策、技术选型、代码模式、API 设计
    "project_docs",  # 需求文档、设计规范、PRD、SOP
    "conversation_history",  # Agent 对话摘要、用户反馈、纠正历史
    "working_methods",  # 最佳实践、工作流程、避坑指南、经验教训
]

TEAM_MEMORY_CATEGORIES: tuple[TeamMemoryCategory, ...] = (
    "code_knowledge",
    "project_docs",
    "conversation_history",
    "working_methods",
)

# 分类中文描述
CATEGORY_LABELS: dict[TeamMemoryCategory, str] = {
    "code_knowledge": "代码知识",
    "project_docs": "项目文档",
    "conversation_history": "历史对话",
    "working_methods": "工作方法",
}

# ── 团队记忆条目 ────────────────────────────────────────────────────────────


class TeamMemoryEntry:
    """一条团队记忆条目"""

    def __init__(
        self,
        content: str,
        category: TeamMemoryCategory,
        agent_name: str | None = None,
        user_id: str | None = None,
        org_id: str | None = None,
        confidence: float = 0.8,
        source: str = "manual",
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ):
        self.id = _generate_memory_id(content, category, org_id)
        self.content = content
        self.category = category
        self.agent_name = agent_name
        self.user_id = user_id
        self.org_id = org_id
        self.confidence = confidence
        self.source = source
        self.metadata = metadata or {}
        self.tags = tags or []
        self.created_at = datetime.now(UTC).isoformat()
        self.updated_at = self.created_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "category": self.category,
            "agent_name": self.agent_name,
            "user_id": self.user_id,
            "org_id": self.org_id,
            "confidence": self.confidence,
            "source": self.source,
            "metadata": self.metadata,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def to_fact_dict(self) -> dict[str, Any]:
        """转换为 DeerMem 兼容的 fact 格式"""
        return {
            "id": self.id,
            "content": self.content,
            "category": self.category,
            "confidence": self.confidence,
            "createdAt": self.created_at,
            "source": json.dumps(
                {
                    "type": self.source,
                    "agent_name": self.agent_name,
                    "org_id": self.org_id,
                    "tags": self.tags,
                    **self.metadata,
                }
            ),
            "scope": {
                "user_id": self.user_id,
                "agent_name": self._team_agent_name(),
                "org_id": self.org_id,
            },
        }

    def _team_agent_name(self) -> str:
        """生成团队命名空间下的 agent_name"""
        if self.org_id:
            return f"team:{self.org_id}"
        return "team:default"


def _generate_memory_id(content: str, category: str, org_id: str | None) -> str:
    """基于内容+分类+团队生成稳定 ID，支持幂等写入"""
    raw = f"{content}|{category}|{org_id or 'default'}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ── 团队记忆管理器 ──────────────────────────────────────────────────────────


class TeamMemoryManager:
    """
    团队长期记忆管理器。

    在现有 MemoryManager 之上叠加团队级记忆，实现：
    - 按 org_id 分桶的团队共享记忆
    - 按 category 分类存储
    - 按 Agent 角色 + 任务语义的按需检索

    底层存储复用 DeerMem（MemoryManager），通过特殊的 agent_name 前缀
    "team:{org_id}" 实现团队命名空间隔离，不改动 DeerMem 核心代码。
    """

    def __init__(self, memory_manager: MemoryManager | None = None):
        self._mm = memory_manager

    @property
    def manager(self) -> MemoryManager:
        if self._mm is None:
            self._mm = get_memory_manager()
        return self._mm

    # ── 写入 ─────────────────────────────────────────────────────────────

    def capture(
        self,
        content: str,
        *,
        category: TeamMemoryCategory = "working_methods",
        agent_name: str | None = None,
        user_id: str | None = None,
        org_id: str | None = None,
        confidence: float = 0.8,
        source: str = "manual",
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> str | None:
        """
        捕获一条团队记忆。

        自动写入两个位置：
        1. Agent 个人记忆（agent_name 维度）— 供该 Agent 后续参考
        2. 团队共享记忆（team:{org_id} 维度）— 供所有 Agent 共享

        返回 memory_id，失败返回 None。
        """
        entry = TeamMemoryEntry(
            content=content,
            category=category,
            agent_name=agent_name,
            user_id=user_id,
            org_id=org_id,
            confidence=confidence,
            source=source,
            metadata=metadata,
            tags=tags,
        )
        fact = entry.to_fact_dict()

        success = False
        try:
            # 写入团队共享命名空间
            team_agent = entry._team_agent_name()
            self.manager.create_fact(
                content=fact["content"],
                category=fact["category"],
                confidence=fact["confidence"],
                agent_name=team_agent,
                user_id=user_id,
            )
            success = True
        except Exception as e:
            logger.warning("Failed to write team memory (team scope): %s", e)

        if agent_name and agent_name != team_agent:
            try:
                # 同时写入 Agent 个人记忆
                self.manager.create_fact(
                    content=fact["content"],
                    category=fact["category"],
                    confidence=fact["confidence"],
                    agent_name=agent_name,
                    user_id=user_id,
                )
            except Exception as e:
                logger.warning("Failed to write team memory (agent scope): %s", e)

        if success:
            logger.info(
                "Team memory captured: category=%s agent=%s org=%s id=%s",
                category,
                agent_name,
                org_id,
                entry.id,
            )
            return entry.id

        return None

    def capture_batch(
        self,
        entries: list[dict[str, Any]],
        *,
        org_id: str | None = None,
        user_id: str | None = None,
    ) -> list[str]:
        """
        批量捕获团队记忆。

        entries: [{"content": "...", "category": "...", "agent_name": "...", ...}, ...]
        返回成功写入的 memory_id 列表。
        """
        ids: list[str] = []
        for entry in entries:
            mid = self.capture(
                content=entry.get("content", ""),
                category=entry.get("category", "working_methods"),
                agent_name=entry.get("agent_name"),
                user_id=entry.get("user_id", user_id),
                org_id=entry.get("org_id", org_id),
                confidence=entry.get("confidence", 0.8),
                source=entry.get("source", "batch"),
                metadata=entry.get("metadata"),
                tags=entry.get("tags"),
            )
            if mid:
                ids.append(mid)
        return ids

    # ── 检索 ─────────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        *,
        org_id: str | None = None,
        category: TeamMemoryCategory | None = None,
        agent_name: str | None = None,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """
        搜索团队记忆。

        优先搜索团队共享记忆（team:{org_id}），
        同时搜索 Agent 个人记忆并合并去重。
        """
        results: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        # 搜索范围：team namespace + agent namespace
        search_scopes: list[str | None] = []
        if org_id:
            search_scopes.append(f"team:{org_id}")
        if agent_name:
            search_scopes.append(agent_name)

        if not search_scopes:
            search_scopes.append(None)  # 全局搜索

        for scope in search_scopes:
            try:
                scope_results = self.manager.search(
                    query,
                    top_k=top_k,
                    agent_name=scope,
                    category=category,
                )
                for r in scope_results:
                    rid = r.get("id", "")
                    if rid and rid not in seen_ids:
                        seen_ids.add(rid)
                        r["_scope"] = "team" if (scope and scope.startswith("team:")) else "agent"
                        results.append(r)
            except Exception as e:
                logger.debug("Memory search failed for scope=%s: %s", scope, e)

        # 按 confidence 降序，取 top_k
        results.sort(key=lambda x: x.get("confidence", 0), reverse=True)
        return results[:top_k]

    def get_by_category(
        self,
        category: TeamMemoryCategory,
        *,
        org_id: str | None = None,
        agent_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """获取指定分类的所有团队记忆"""
        return self.search(
            query="",  # 空查询 = 获取全部
            org_id=org_id,
            category=category,
            agent_name=agent_name,
            top_k=50,
        )

    # ── 装配（按角色+任务组装上下文） ─────────────────────────────────────

    def assemble(
        self,
        *,
        org_id: str | None = None,
        agent_role: str | None = None,
        task: str = "",
        user_id: str | None = None,
        max_facts: int = 15,
    ) -> str:
        """
        按 Agent 角色 + 任务描述装配记忆上下文。

        策略：
        1. 获取团队共享记忆（所有 Agent 都能看到）
        2. 获取 Agent 专属记忆（该角色的经验积累）
        3. 按任务语义相关性排序
        4. 按分类组织输出

        返回注入就绪的文本（可直接拼入 system prompt）。
        """
        if not org_id and not agent_role:
            return ""

        # 1. 搜索团队记忆
        team_results = self.search(
            query=task,
            org_id=org_id,
            top_k=max_facts,
        )

        # 2. 搜索 Agent 专属记忆
        agent_results: list[dict[str, Any]] = []
        if agent_role:
            agent_results = self.search(
                query=task,
                agent_name=agent_role,
                top_k=max_facts // 2,
            )

        # 3. 合并去重
        all_results = team_results + agent_results
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for r in all_results:
            rid = r.get("id", "")
            if rid and rid not in seen:
                seen.add(rid)
                unique.append(r)

        # 4. 按分类分组
        grouped: dict[str, list[str]] = {}
        for r in unique:
            cat = r.get("category", "context")
            content = r.get("content", "")
            if content:
                grouped.setdefault(cat, []).append(content)

        # 5. 格式化输出
        sections: list[str] = []
        section_order = [
            ("working_methods", "## 工作方法与最佳实践"),
            ("code_knowledge", "## 代码与架构知识"),
            ("project_docs", "## 项目文档与规范"),
            ("conversation_history", "## 历史经验与反馈"),
        ]

        for cat, title in section_order:
            items = grouped.get(cat, [])
            if items:
                sections.append(title)
                for item in items[:5]:
                    sections.append(f"- {item}")
                sections.append("")

        # 其他分类
        for cat, items in grouped.items():
            if cat not in dict(section_order):
                sections.append(f"## {CATEGORY_LABELS.get(cat, cat)}")
                for item in items[:5]:
                    sections.append(f"- {item}")
                sections.append("")

        if not sections:
            return ""

        return "\n".join(sections)

    # ── 管理 ─────────────────────────────────────────────────────────────

    def clear_team_memory(
        self,
        org_id: str,
        *,
        user_id: str | None = None,
    ) -> bool:
        """清除指定团队的所有记忆"""
        try:
            team_agent = f"team:{org_id}"
            self.manager.clear_memory(agent_name=team_agent, user_id=user_id)
            logger.info("Team memory cleared for org=%s", org_id)
            return True
        except Exception as e:
            logger.error("Failed to clear team memory for org=%s: %s", org_id, e)
            return False

    def export_team_memory(
        self,
        org_id: str,
        *,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """导出团队记忆"""
        try:
            team_agent = f"team:{org_id}"
            return self.manager.get_memory(agent_name=team_agent, user_id=user_id)
        except Exception as e:
            logger.error("Failed to export team memory for org=%s: %s", org_id, e)
            return {}


# ── 单例缓存 ─────────────────────────────────────────────────────────────────

_team_memory_manager: TeamMemoryManager | None = None


def get_team_memory_manager() -> TeamMemoryManager:
    """获取 TeamMemoryManager 单例"""
    global _team_memory_manager
    if _team_memory_manager is None:
        _team_memory_manager = TeamMemoryManager()
    return _team_memory_manager


def reset_team_memory_manager() -> None:
    """重置单例（测试用）"""
    global _team_memory_manager
    _team_memory_manager = None
