"""Tests for Phase 3 helpers: tool ranking + chat signal mining."""

from __future__ import annotations

from deerflow.hoh import (
    ChatSignal,
    ToolSignal,
    rank_tools,
    signals_to_evidence,
)
from deerflow.hoh.types import EvidenceType


def test_rank_tools_prefers_high_failure_rate():
    signals = [
        ToolSignal(name="good", failure_rate=0.01, active_users=100, complaint_count=0),
        ToolSignal(name="bad", failure_rate=0.6, active_users=50, complaint_count=5),
    ]
    ranked = rank_tools(signals, top_k=2)
    assert ranked[0][0].name == "bad"
    assert ranked[1][0].name == "good"


def test_chat_signals_become_gap_evidence():
    sigs = [
        ChatSignal(thread_id="t1", user_id="u1", tool_name="x", signal="thumbs_down"),
        ChatSignal(thread_id="t2", user_id="u2", tool_name="y", signal="retry", detail="3 retries"),
    ]
    evs = signals_to_evidence(sigs)
    assert len(evs) == 2
    assert all(e.type == EvidenceType.GAP for e in evs)
    assert "thumbs_down" in evs[0].description
