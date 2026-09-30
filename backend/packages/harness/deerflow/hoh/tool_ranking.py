"""Tool marketplace priority ranking.

Part of HoH Phase 3a: surfaces user friction as Evidence so the Planner
can decide which skill to improve next.

Score formula (per design doc):
    priority = w1 * failure_rate + w2 * log(active_users + 1)
             + w3 * complaint_count - w4 * recency_bonus

Defaults: w1=0.5, w2=0.2, w3=0.2, w4=0.1
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class ToolSignal:
    name: str
    failure_rate: float  # 0..1
    active_users: int
    complaint_count: int
    days_since_last_used: int = 0


def rank_tools(signals: list[ToolSignal], top_k: int = 10) -> list[tuple[ToolSignal, float]]:
    """Return tools sorted by priority desc, with their score."""
    scored = []
    for s in signals:
        recency = 1.0 if s.days_since_last_used <= 7 else 0.3
        score = 0.5 * s.failure_rate + 0.2 * math.log(s.active_users + 1) + 0.2 * s.complaint_count - 0.1 * recency
        scored.append((s, round(score, 4)))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]
