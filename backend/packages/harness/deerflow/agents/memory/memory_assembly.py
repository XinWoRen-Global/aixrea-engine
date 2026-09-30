"""
记忆装配服务 — Memory Assembly Service

按 Agent 角色 + 任务语义，从团队记忆库中检索相关记忆并组装为上下文。

核心能力：
  1. 角色感知检索 — 不同 Agent 角色获取不同侧重点的记忆
  2. 任务语义匹配 — 根据任务描述检索最相关的记忆
  3. 上下文组装 — 将检索结果格式化为可注入 system prompt 的文本
  4. 优先级排序 — 高置信度 + 最近更新 + 角色相关性

Agent 角色映射：
  ┌──────────────────┬──────────────────────────────────────┐
  │ drama-executor   │ 短剧管线：剧本分析、角色生成、视频合成 │
  │ comic-executor   │ 漫画管线：分镜、风格、排版            │
  │ music-executor   │ 音乐管线：作曲、编曲、混音            │
  │ game-executor    │ 互动影游：剧本、分支、引擎            │
  │ lead-agent       │ 通用对话：路由、分析、推荐            │
  └──────────────────┴──────────────────────────────────────┘

用法：
  from deerflow.agents.memory.memory_assembly import MemoryAssembly

  assembly = MemoryAssembly(org_id="org_xxx")
  context = await assembly.assemble_for_agent(
      agent_role="drama-executor",
      task="生成12集都市爱情短剧，9:16竖屏，60秒/集",
  )
  # context 可以直接注入到 system prompt 中
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from deerflow.agents.memory.team_memory import (
    TeamMemoryCategory,
    TeamMemoryManager,
    get_team_memory_manager,
)

logger = logging.getLogger("memory_assembly")

# ── Agent 角色定义 ───────────────────────────────────────────────────────────


@dataclass
class AgentRoleProfile:
    """Agent 角色的记忆检索偏好"""

    role_id: str
    display_name: str
    # 该角色最关注的记忆分类（按优先级排序）
    priority_categories: list[TeamMemoryCategory]
    # 该角色相关的搜索关键词
    search_keywords: list[str]
    # 最大记忆数
    max_facts: int = 15


# 角色配置表
AGENT_ROLE_PROFILES: dict[str, AgentRoleProfile] = {
    "drama-executor": AgentRoleProfile(
        role_id="drama-executor",
        display_name="短剧管线执行器",
        priority_categories=[
            "working_methods",
            "code_knowledge",
            "conversation_history",
            "project_docs",
        ],
        search_keywords=[
            "短剧",
            "drama",
            "视频生成",
            "角色一致性",
            "分镜",
            "剧本分析",
            "风格",
            "分辨率",
            "时长",
            "集数",
            "video generation",
            "character consistency",
            "storyboard",
        ],
        max_facts=15,
    ),
    "comic-executor": AgentRoleProfile(
        role_id="comic-executor",
        display_name="漫画管线执行器",
        priority_categories=[
            "working_methods",
            "code_knowledge",
            "conversation_history",
        ],
        search_keywords=[
            "漫画",
            "comic",
            "分镜",
            "画风",
            "排版",
            "角色设计",
            "comic style",
            "panel layout",
            "character design",
        ],
        max_facts=12,
    ),
    "music-executor": AgentRoleProfile(
        role_id="music-executor",
        display_name="音乐管线执行器",
        priority_categories=[
            "working_methods",
            "code_knowledge",
            "conversation_history",
        ],
        search_keywords=[
            "音乐",
            "music",
            "作曲",
            "编曲",
            "混音",
            "BGM",
            "composition",
            "arrangement",
            "mixing",
        ],
        max_facts=12,
    ),
    "game-executor": AgentRoleProfile(
        role_id="game-executor",
        display_name="互动影游管线执行器",
        priority_categories=[
            "working_methods",
            "code_knowledge",
            "project_docs",
        ],
        search_keywords=[
            "互动影游",
            "interactive",
            "分支剧情",
            "游戏引擎",
            "branching narrative",
            "game engine",
        ],
        max_facts=12,
    ),
    "lead-agent": AgentRoleProfile(
        role_id="lead-agent",
        display_name="通用对话 Lead Agent",
        priority_categories=[
            "conversation_history",
            "working_methods",
            "project_docs",
        ],
        search_keywords=[
            "用户偏好",
            "项目",
            "推荐",
            "分析",
            "配置",
            "user preference",
            "project",
            "recommendation",
        ],
        max_facts=10,
    ),
}


def get_agent_profile(agent_role: str) -> AgentRoleProfile:
    """获取 Agent 角色配置，未注册角色返回通用配置"""
    return AGENT_ROLE_PROFILES.get(
        agent_role,
        AgentRoleProfile(
            role_id=agent_role,
            display_name=agent_role,
            priority_categories=["working_methods", "conversation_history"],
            search_keywords=[],
            max_facts=10,
        ),
    )


# ── 记忆装配服务 ─────────────────────────────────────────────────────────────


class MemoryAssembly:
    """
    记忆装配服务。

    根据 Agent 角色和任务描述，从团队记忆库中检索相关记忆，
    组装为可注入 system prompt 的上下文文本。

    装配策略：
    1. 角色筛选 — 优先返回该角色关注的记忆分类
    2. 任务匹配 — 用任务描述做语义搜索
    3. 关键词增强 — 补充角色相关的关键词搜索
    4. 分层组织 — 团队记忆 → Agent 专属记忆 → 按分类排序
    """

    def __init__(
        self,
        org_id: str | None = None,
        team_memory: TeamMemoryManager | None = None,
    ):
        self.org_id = org_id
        self._tm = team_memory

    @property
    def tm(self) -> TeamMemoryManager:
        if self._tm is None:
            self._tm = get_team_memory_manager()
        return self._tm

    async def assemble_for_agent(
        self,
        agent_role: str,
        task: str = "",
        *,
        org_id: str | None = None,
        user_id: str | None = None,
        max_tokens: int = 2000,
    ) -> str:
        """
        为指定 Agent 角色装配记忆上下文。

        Args:
            agent_role: Agent 角色 ID（如 "drama-executor"）
            task: 当前任务描述（用于语义检索）
            org_id: 团队 ID（覆盖实例默认值）
            user_id: 用户 ID
            max_tokens: 最大 token 数（近似限制）

        Returns:
            注入就绪的上下文文本（可直接拼入 system prompt）
        """
        effective_org = org_id or self.org_id
        if not effective_org:
            logger.debug("No org_id provided, skipping memory assembly")
            return ""

        profile = get_agent_profile(agent_role)

        # 1. 搜索团队共享记忆
        all_facts: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        # 用任务描述搜索
        if task:
            task_results = self.tm.search(
                query=task,
                org_id=effective_org,
                agent_name=agent_role,
                top_k=profile.max_facts,
            )
            for r in task_results:
                rid = r.get("id", "")
                if rid and rid not in seen_ids:
                    seen_ids.add(rid)
                    all_facts.append(r)

        # 用角色关键词补充搜索
        for keyword in profile.search_keywords[:5]:
            kw_results = self.tm.search(
                query=keyword,
                org_id=effective_org,
                agent_name=agent_role,
                top_k=5,
            )
            for r in kw_results:
                rid = r.get("id", "")
                if rid and rid not in seen_ids:
                    seen_ids.add(rid)
                    all_facts.append(r)

        if not all_facts:
            return ""

        # 2. 按角色优先分类排序
        cat_priority = {cat: i for i, cat in enumerate(profile.priority_categories)}
        all_facts.sort(
            key=lambda f: (
                cat_priority.get(f.get("category", ""), 99),  # 分类优先级
                -(f.get("confidence", 0)),  # 置信度降序
            )
        )

        # 3. 限制数量
        all_facts = all_facts[: profile.max_facts]

        # 4. 按分类分组
        grouped: dict[str, list[str]] = {}
        for f in all_facts:
            cat = f.get("category", "context")
            content = f.get("content", "")
            if content:
                grouped.setdefault(cat, []).append(content)

        # 5. 格式化输出
        return self._format_context(
            grouped,
            profile,
            max_tokens=max_tokens,
        )

    def assemble_sync(
        self,
        agent_role: str,
        task: str = "",
        *,
        org_id: str | None = None,
        user_id: str | None = None,
        max_tokens: int = 2000,
    ) -> str:
        """同步版本的 assemble_for_agent（用于非 async 上下文）"""
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None:
            # 已在事件循环中，使用 run_in_executor
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    lambda: asyncio.run(
                        self.assemble_for_agent(
                            agent_role=agent_role,
                            task=task,
                            org_id=org_id,
                            user_id=user_id,
                            max_tokens=max_tokens,
                        )
                    )
                )
                return future.result(timeout=10)
        else:
            return asyncio.run(
                self.assemble_for_agent(
                    agent_role=agent_role,
                    task=task,
                    org_id=org_id,
                    user_id=user_id,
                    max_tokens=max_tokens,
                )
            )

    def _format_context(
        self,
        grouped: dict[str, list[str]],
        profile: AgentRoleProfile,
        max_tokens: int = 2000,
    ) -> str:
        """将分组记忆格式化为上下文文本"""
        from deerflow.agents.memory.team_memory import CATEGORY_LABELS

        sections: list[str] = []
        sections.append(f"<!-- 团队长期记忆 ({profile.display_name}) -->")

        total_chars = 0
        char_limit = max_tokens * 3  # 粗略估算：1 token ≈ 3 chars

        for cat in profile.priority_categories:
            items = grouped.get(cat, [])
            if not items:
                continue

            label = CATEGORY_LABELS.get(cat, cat)
            sections.append(f"\n## {label}")

            for item in items[:5]:
                line = f"- {item}"
                if total_chars + len(line) > char_limit:
                    sections.append(f"- ... (更多记忆已截断，共 {len(items)} 条)")
                    break
                sections.append(line)
                total_chars += len(line)

        return "\n".join(sections)


# ── 单例 ─────────────────────────────────────────────────────────────────────

_assembly: MemoryAssembly | None = None


def get_memory_assembly(org_id: str | None = None) -> MemoryAssembly:
    """获取 MemoryAssembly 实例"""
    global _assembly
    if _assembly is None or (org_id and _assembly.org_id != org_id):
        _assembly = MemoryAssembly(org_id=org_id)
    return _assembly


def reset_memory_assembly() -> None:
    """重置单例（测试用）"""
    global _assembly
    _assembly = None
