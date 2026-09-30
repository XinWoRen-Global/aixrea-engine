"""End-to-end dry-run of the drama HoH loop.

Uses:
  - LLMPlanner with a stubbed chat callable (no real LLM)
  - DramaDeveloper in dry-run mode (no real PipelineExecutor)
  - DramaQATester (real rules)
  - InMemoryEvidenceStore

This proves the loop contract end-to-end without external services.
"""

from __future__ import annotations

import json

import pytest

from deerflow.hoh import (
    Artifact,
    HohOrchestrator,
    InMemoryEvidenceStore,
)
from deerflow.hoh.drama_developer import DramaDeveloper
from deerflow.hoh.llm_planner import LLMPlanner
from deerflow.hoh.qa_drama import DramaQATester
from deerflow.hoh.types import EvidenceType


def _stub_chat_factory():
    """Return a chat callable that always proposes a valid candidate."""
    calls = {"n": 0}

    async def chat(_prompt: str) -> str:
        calls["n"] += 1
        return json.dumps(
            {
                "scope": f"increment-{calls['n']}",
                "acceptance": ["duration in 60-180"],
                "preserve": ["style"],
                "estimated_cost_usd": 0.4,
            }
        )

    return chat, calls


@pytest.mark.asyncio
async def test_drama_loop_dry_run_end_to_end():
    chat, calls = _stub_chat_factory()
    store = InMemoryEvidenceStore()
    orch = HohOrchestrator(
        planner=LLMPlanner(chat=chat),
        developer=DramaDeveloper(),  # dry-run mode
        qa=DramaQATester(),
        evidence_store=store,
    )
    results = await orch.run(
        module="drama",
        spec="60s cyberpunk short drama",
        initial_artifact=Artifact(module="drama", version=0),
        max_iterations=2,
    )
    assert len(results) == 2
    assert calls["n"] == 2  # one LLM call per loop
    # First loop: dry-run artifact has no metric -> all GAP
    first_gaps = [e for e in results[0].evidence if e.type == EvidenceType.GAP]
    assert len(first_gaps) == 4


@pytest.mark.asyncio
async def test_llm_planner_parses_json_with_extra_text():
    async def chat(_prompt):
        return 'Here is the plan: {"scope": "add opening scene", "acceptance": ["3 shots"], "preserve": ["characters"]}'

    p = LLMPlanner(chat=chat)
    doc = await p.plan(
        module="drama",
        spec="s",
        prior_evidence=[],
        current_artifact=Artifact(module="drama", version=1),
        iteration=3,
    )
    assert doc.scope == "add opening scene"
    assert doc.iteration == 3
    assert doc.preserve == ["characters"]
