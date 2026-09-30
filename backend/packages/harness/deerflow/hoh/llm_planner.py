"""LLM-backed Project Planner.

Reads prior evidence + current artifact and produces the next bounded
increment D_t. Uses a cheap model (Phase 1) to keep cost low.

Phase 1: skeleton. The prompt template is ready; the actual LLM call
is injected via a ``chat`` callable so tests can stub it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from .types import Artifact, DevDoc, Evidence

DEFAULT_SYSTEM = """You are the Project Planner for the drama module of an AI content platform.
Your job: read the high-level spec, prior evidence, and current artifact,
then decide ONE bounded increment for the next loop.

Rules:
- The increment must be locally complete (observable acceptance).
- Balance repair and capability growth: if last loop added a feature,
  this loop may fix its gaps; if last loop was pure repair, this loop
  must add a new capability.
- List behaviors that must be preserved.
- Output JSON only.
"""

PromptFn = Callable[[str], Awaitable[str]]


class LLMPlanner:
    """Produces DevDoc via an injected chat callable."""

    def __init__(self, chat: PromptFn, model_name: str = "cheap-default") -> None:
        self._chat = chat
        self.model_name = model_name

    async def plan(
        self,
        module: str,
        spec: str,
        prior_evidence: list[Evidence],
        current_artifact: Artifact,
        iteration: int,
    ) -> DevDoc:
        user_msg = self._build_prompt(spec, prior_evidence, current_artifact, iteration)
        raw = await self._chat(user_msg)
        return self._parse(raw, module, iteration)

    @staticmethod
    def _build_prompt(
        spec: str,
        prior_evidence: list[Evidence],
        current: Artifact,
        iteration: int,
    ) -> str:
        ev_lines = "\n".join(f"- [{e.type.value}] it={e.iteration} {e.description}" for e in prior_evidence[-20:]) or "- (none)"
        return (
            f"Spec: {spec}\n"
            f"Current artifact version: {current.version}\n"
            f"Iteration: {iteration}\n"
            f"Prior evidence (last 20):\n{ev_lines}\n\n"
            "Respond with JSON:\n"
            '{"scope": "...", "acceptance": ["..."], "preserve": ["..."], "estimated_cost_usd": 0.5}'
        )

    @staticmethod
    def _parse(raw: str, module: str, iteration: int) -> DevDoc:
        import json
        import re

        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            # Fallback: conservative default
            return DevDoc(
                module=module,
                iteration=iteration,
                scope="continue current increment",
                acceptance=["no regression in verified behaviors"],
            )
        data = json.loads(m.group(0))
        return DevDoc(
            module=module,
            iteration=iteration,
            scope=data.get("scope", "continue"),
            acceptance=list(data.get("acceptance", [])),
            preserve=list(data.get("preserve", [])),
            estimated_cost_usd=float(data.get("estimated_cost_usd", 0.5)),
        )
