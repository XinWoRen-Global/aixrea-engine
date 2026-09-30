"""
团队记忆工具 — Team Memory Tools for DeerFlow Agents

提供给 DeerFlow Agent 在运行时调用的记忆工具。
Agent 可以通过这些工具：
  1. team_memory_search — 搜索团队记忆库
  2. team_memory_add — 添加新的团队记忆
  3. team_memory_context — 获取当前任务的记忆上下文

这些工具与 deerflow.agents.memory.tools 中的个人记忆工具互补：
  - memory_search / memory_add: 个人记忆（per-user, per-agent）
  - team_memory_*: 团队共享记忆（per-org, cross-agent）

用法（在 Agent 配置中注册）：
  from deerflow.agents.memory.team_memory_tools import get_team_memory_tools
  tools = get_team_memory_tools(org_id="org_xxx", agent_role="drama-executor")
"""

from __future__ import annotations

import json
import logging

from langchain.tools import tool

from deerflow.agents.memory.memory_assembly import get_memory_assembly
from deerflow.agents.memory.team_memory import get_team_memory_manager
from deerflow.tools.types import Runtime

logger = logging.getLogger("team_memory_tools")


def _resolve_org_and_role(runtime: Runtime | None = None) -> tuple[str | None, str | None]:
    """从 runtime context 中解析 org_id 和 agent_role"""
    context = getattr(runtime, "context", None)
    if isinstance(context, dict):
        return (
            context.get("org_id"),
            context.get("agent_name") or context.get("agent_role"),
        )
    return None, None


@tool("team_memory_search", parse_docstring=True)
def team_memory_search_tool(
    runtime: Runtime,
    query: str,
    category: str | None = None,
    limit: int = 10,
) -> str:
    """搜索团队共享记忆库。

    使用此工具查找团队积累的代码知识、项目文档、历史经验和工作方法。
    与 memory_search（个人记忆）不同，此工具搜索的是整个团队共享的记忆。

    Args:
        query: 自然语言搜索查询。例如 "短剧角色一致性最佳实践" 或 "上次视频生成失败的原因"
        category: 可选分类过滤。可选值: code_knowledge, project_docs, conversation_history, working_methods
        limit: 最大返回结果数 (默认 10)

    Returns:
        JSON string with "results" (list of memory entries) and "count".
        每个条目包含 content, category, confidence, source, tags。
    """
    org_id, agent_role = _resolve_org_and_role(runtime)
    tm = get_team_memory_manager()

    try:
        results = tm.search(
            query=query,
            org_id=org_id,
            category=category,
            agent_name=agent_role,
            top_k=limit,
        )
        return json.dumps({"results": results, "count": len(results)}, ensure_ascii=False, default=str)
    except Exception as exc:
        logger.exception("team_memory_search_tool failed")
        return json.dumps({"error": str(exc)})


@tool("team_memory_add", parse_docstring=True)
def team_memory_add_tool(
    runtime: Runtime,
    content: str,
    category: str = "working_methods",
    confidence: float = 0.8,
    tags: str = "",
) -> str:
    """向团队记忆库添加一条新记忆。

    当你发现重要的知识、经验教训、或工作方法时，使用此工具将其保存到团队记忆库，
    供所有团队成员和 Agent 后续参考。

    Args:
        content: 记忆内容。要具体、可操作。例如 "短剧角色一致性: 同剧集使用相同 seed，避免角色漂移"
        category: 记忆分类。可选值:
            code_knowledge - 代码知识、架构决策
            project_docs - 项目文档、需求规范
            conversation_history - 历史对话、用户反馈
            working_methods - 工作方法、最佳实践
        confidence: 置信度 0.0-1.0 (默认 0.8)。确定的事实用高值，推测用低值。
        tags: 逗号分隔的标签，用于后续检索。例如 "drama,character,consistency"

    Returns:
        JSON string with "memory_id" and "status": "added"。
    """
    org_id, agent_role = _resolve_org_and_role(runtime)
    tm = get_team_memory_manager()

    try:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

        memory_id = tm.capture(
            content=content.strip(),
            category=category,
            agent_name=agent_role,
            org_id=org_id,
            confidence=confidence,
            source="agent_tool",
            tags=tag_list,
        )

        if memory_id:
            return json.dumps({"memory_id": memory_id, "status": "added"})
        return json.dumps({"error": "Failed to add memory"})
    except Exception as exc:
        logger.exception("team_memory_add_tool failed")
        return json.dumps({"error": str(exc)})


@tool("team_memory_context", parse_docstring=True)
def team_memory_context_tool(
    runtime: Runtime,
    task: str = "",
) -> str:
    """获取当前任务的团队记忆上下文。

    自动根据你的 Agent 角色和当前任务，从团队记忆库中检索最相关的记忆，
    组装为可直接使用的上下文。在执行复杂任务前调用此工具，
    可以获取团队积累的知识和经验。

    Args:
        task: 当前任务描述（可选）。提供任务描述可以获得更精准的记忆匹配。
            例如 "生成12集都市爱情短剧，9:16竖屏，60秒/集"

    Returns:
        格式化的记忆上下文文本，可直接用于辅助决策。
    """
    org_id, agent_role = _resolve_org_and_role(runtime)

    if not org_id or not agent_role:
        return json.dumps({"error": "org_id and agent_role are required for team memory context"})

    try:
        assembly = get_memory_assembly(org_id=org_id)
        context = assembly.assemble_sync(
            agent_role=agent_role,
            task=task,
            org_id=org_id,
        )
        if context:
            return context
        return json.dumps({"message": "No relevant team memory found for this task"})
    except Exception as exc:
        logger.exception("team_memory_context_tool failed")
        return json.dumps({"error": str(exc)})


def get_team_memory_tools(
    org_id: str | None = None,
    agent_role: str | None = None,
) -> list:
    """
    返回所有团队记忆工具，供 Agent 注册。

    在 Agent 配置中调用：
      tools = get_team_memory_tools(org_id="org_xxx", agent_role="drama-executor")

    Args:
        org_id: 团队 ID（用于记忆隔离）
        agent_role: Agent 角色（用于按需装配）

    Returns:
        LangChain tool 列表
    """
    return [
        team_memory_search_tool,
        team_memory_add_tool,
        team_memory_context_tool,
    ]
