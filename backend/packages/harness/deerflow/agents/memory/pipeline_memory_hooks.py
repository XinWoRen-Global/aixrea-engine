"""
Pipeline 记忆自动采集 Hook — Pipeline Memory Hooks

在 Pipeline Executor 执行过程中自动捕获团队知识，无需手动操作。

捕获时机：
  1. Album 开始执行 → 记录项目配置、参数选择
  2. 节点执行成功 → 记录产出摘要、模型选择、耗时
  3. 节点执行失败 → 记录错误模式、恢复策略
  4. Album 完成 → 记录整体统计、经验教训

捕获的记忆分类：
  - working_methods:    参数选择策略、工作流优化
  - code_knowledge:     模型路由决策、API 调用模式
  - conversation_history: 执行摘要、用户反馈

用法：
  from deerflow.agents.memory.pipeline_memory_hooks import PipelineMemoryHooks

  hooks = PipelineMemoryHooks(org_id="org_xxx")

  # 在 PipelineExecutor.execute_album() 中：
  await hooks.on_album_start(album, user_id)
  await hooks.on_node_complete(node, result, user_id)
  await hooks.on_node_error(node, error, user_id)
  await hooks.on_album_complete(album, summary, user_id)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from deerflow.agents.memory.team_memory import TeamMemoryManager, get_team_memory_manager

logger = logging.getLogger("pipeline.memory_hooks")


class PipelineMemoryHooks:
    """
    Pipeline 执行记忆自动采集器。

    非阻塞设计：所有 capture 调用都是 fire-and-forget，
    不会阻塞 Pipeline 主流程。失败时仅记录日志，不影响管线执行。
    """

    def __init__(
        self,
        org_id: str | None = None,
        agent_name: str = "drama-executor",
        team_memory: TeamMemoryManager | None = None,
        enabled: bool = True,
    ):
        self.org_id = org_id
        self.agent_name = agent_name
        self._tm = team_memory
        self.enabled = enabled
        self._album_start_time: dict[str, datetime] = {}

    @property
    def tm(self) -> TeamMemoryManager:
        if self._tm is None:
            self._tm = get_team_memory_manager()
        return self._tm

    def _should_capture(self) -> bool:
        return self.enabled and self.org_id is not None

    # ── Album 生命周期 ──────────────────────────────────────────────────

    async def on_album_start(self, album: dict, user_id: str) -> None:
        """Album 开始执行时捕获项目配置"""
        if not self._should_capture():
            return

        album_id = album.get("id", "")
        self._album_start_time[album_id] = datetime.now(UTC)

        album_type = album.get("album_type", "unknown")
        config = album.get("config", {})

        try:
            # 记录项目配置决策
            config_summary = self._summarize_config(config, album_type)
            if config_summary:
                self.tm.capture(
                    content=f"[{album_type}] 项目配置: {config_summary}",
                    category="working_methods",
                    agent_name=self.agent_name,
                    user_id=user_id,
                    org_id=self.org_id,
                    confidence=0.9,
                    source="pipeline_album_start",
                    metadata={"album_id": album_id, "album_type": album_type},
                    tags=["pipeline", album_type, "config"],
                )
        except Exception as e:
            logger.debug("Pipeline memory hook (album_start) failed: %s", e)

    async def on_node_complete(
        self,
        node: dict,
        result: dict | None,
        user_id: str,
        album: dict | None = None,
    ) -> None:
        """节点执行成功时捕获产出摘要"""
        if not self._should_capture():
            return

        node_type = node.get("node_type", "")
        node_id = node.get("id", "")
        album_id = node.get("album_id", "")

        try:
            # 记录节点执行结果
            summary = self._summarize_node_result(node_type, result)
            if summary:
                self.tm.capture(
                    content=f"[{node_type}] {summary}",
                    category="working_methods",
                    agent_name=self.agent_name,
                    user_id=user_id,
                    org_id=self.org_id,
                    confidence=0.85,
                    source="pipeline_node_complete",
                    metadata={
                        "node_id": node_id,
                        "node_type": node_type,
                        "album_id": album_id,
                    },
                    tags=["pipeline", node_type, "success"],
                )
        except Exception as e:
            logger.debug("Pipeline memory hook (node_complete) failed: %s", e)

    async def on_node_error(
        self,
        node: dict,
        error: Exception | str,
        user_id: str,
        album: dict | None = None,
    ) -> None:
        """节点执行失败时捕获错误模式"""
        if not self._should_capture():
            return

        node_type = node.get("node_type", "")
        node_id = node.get("id", "")
        album_id = node.get("album_id", "")
        error_str = str(error)[:300]

        try:
            # 记录错误模式，供后续 Agent 避坑
            self.tm.capture(
                content=f"[{node_type}] 执行失败: {error_str}",
                category="working_methods",
                agent_name=self.agent_name,
                user_id=user_id,
                org_id=self.org_id,
                confidence=0.7,
                source="pipeline_node_error",
                metadata={
                    "node_id": node_id,
                    "node_type": node_type,
                    "album_id": album_id,
                    "error": error_str,
                },
                tags=["pipeline", node_type, "error", "troubleshooting"],
            )
        except Exception as e:
            logger.debug("Pipeline memory hook (node_error) failed: %s", e)

    async def on_album_complete(
        self,
        album: dict,
        summary: dict | None = None,
        user_id: str = "",
    ) -> None:
        """Album 执行完成时捕获整体统计和经验"""
        if not self._should_capture():
            return

        album_id = album.get("id", "")
        album_type = album.get("album_type", "unknown")
        status = album.get("status", "unknown")

        # 计算耗时
        start_time = self._album_start_time.pop(album_id, None)
        duration_sec = None
        if start_time:
            duration_sec = (datetime.now(UTC) - start_time).total_seconds()

        try:
            # 记录执行摘要
            duration_str = f"耗时 {duration_sec:.0f}秒" if duration_sec else ""
            status_str = "成功" if status == "completed" else f"部分失败 (status={status})"

            self.tm.capture(
                content=f"[{album_type}] 管线执行完成: {status_str} {duration_str}",
                category="conversation_history",
                agent_name=self.agent_name,
                user_id=user_id,
                org_id=self.org_id,
                confidence=0.95,
                source="pipeline_album_complete",
                metadata={
                    "album_id": album_id,
                    "album_type": album_type,
                    "status": status,
                    "duration_sec": duration_sec,
                },
                tags=["pipeline", album_type, "summary"],
            )

            # 如果有 summary，记录关键经验
            if summary:
                lessons = summary.get("lessons", [])
                for lesson in lessons[:3]:
                    self.tm.capture(
                        content=f"[{album_type}] 经验教训: {lesson}",
                        category="working_methods",
                        agent_name=self.agent_name,
                        user_id=user_id,
                        org_id=self.org_id,
                        confidence=0.8,
                        source="pipeline_album_summary",
                        metadata={"album_id": album_id},
                        tags=["pipeline", album_type, "lesson"],
                    )
        except Exception as e:
            logger.debug("Pipeline memory hook (album_complete) failed: %s", e)

    async def on_model_choice(
        self,
        node_type: str,
        model_name: str,
        reason: str,
        user_id: str = "",
        album_id: str = "",
    ) -> None:
        """记录模型路由决策"""
        if not self._should_capture():
            return

        try:
            self.tm.capture(
                content=f"[{node_type}] 模型选择: {model_name} — {reason}",
                category="code_knowledge",
                agent_name=self.agent_name,
                user_id=user_id,
                org_id=self.org_id,
                confidence=0.9,
                source="pipeline_model_choice",
                metadata={
                    "node_type": node_type,
                    "model_name": model_name,
                    "album_id": album_id,
                },
                tags=["pipeline", "model-routing", node_type],
            )
        except Exception as e:
            logger.debug("Pipeline memory hook (model_choice) failed: %s", e)

    # ── 辅助方法 ────────────────────────────────────────────────────────

    def _summarize_config(self, config: dict | None, album_type: str) -> str:
        """从 album config 中提取关键参数摘要"""
        if not config:
            return ""

        parts = []
        key_params = {
            "drama": ["style", "episodes", "aspectRatio", "duration", "resolution"],
            "comic": ["style", "pages", "format"],
            "music": ["genre", "duration", "mood"],
            "game": ["genre", "platform", "complexity"],
        }

        params = key_params.get(album_type, ["style", "format"])
        for key in params:
            val = config.get(key)
            if val:
                parts.append(f"{key}={val}")

        return ", ".join(parts) if parts else ""

    def _summarize_node_result(self, node_type: str, result: dict | None) -> str:
        """从节点执行结果中提取摘要"""
        if not result:
            return f"{node_type} 执行完成"

        parts = []
        if "output_url" in result:
            parts.append("产出已上传")
        if "asset_count" in result:
            parts.append(f"生成 {result['asset_count']} 个资产")
        if "model_used" in result:
            parts.append(f"模型: {result['model_used']}")
        if "duration_ms" in result:
            parts.append(f"耗时 {result['duration_ms']}ms")

        if parts:
            return f"{node_type} 执行完成: " + ", ".join(parts)
        return f"{node_type} 执行完成"


# ── 单例 ─────────────────────────────────────────────────────────────────────

_pipeline_hooks: PipelineMemoryHooks | None = None


def get_pipeline_memory_hooks(
    org_id: str | None = None,
    agent_name: str = "drama-executor",
) -> PipelineMemoryHooks:
    """获取 PipelineMemoryHooks 实例"""
    global _pipeline_hooks
    if _pipeline_hooks is None:
        _pipeline_hooks = PipelineMemoryHooks(
            org_id=org_id,
            agent_name=agent_name,
        )
    return _pipeline_hooks
