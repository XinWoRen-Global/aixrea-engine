"""Chat signal mining for /ai.

Part of HoH Phase 3b: mines user feedback signals from chat threads
and emits Evidence entries. Signals:
  - thumbs_down on a tool response
  - repeated retries (>2) on the same task
  - abandoned task (user closes tab before final response)
  - explicit "that's wrong" / "try again" in user message

These become GAP evidence entries that Planner reads next loop.
"""

from __future__ import annotations

from dataclasses import dataclass

from .types import Evidence, EvidenceType


@dataclass
class ChatSignal:
    thread_id: str
    user_id: str
    tool_name: str
    signal: str  # thumbs_down | retry | abandon | correction
    detail: str = ""
    iteration_hint: int = 0


def signals_to_evidence(signals: list[ChatSignal], module: str = "chat") -> list[Evidence]:
    """Convert raw chat signals into Evidence entries."""
    out: list[Evidence] = []
    for s in signals:
        out.append(
            Evidence(
                module=module,
                iteration=s.iteration_hint,
                type=EvidenceType.GAP,
                description=f"signal:{s.signal} tool={s.tool_name} thread={s.thread_id} {s.detail}",
            )
        )
    return out
