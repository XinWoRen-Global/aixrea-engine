"""Skeleton tests for the HoH orchestrator.

Phase 0: no DB, no real adapters. We use stub roles to verify the
planner -> developer -> QA loop contracts and evidence persistence.
"""

from __future__ import annotations

import pytest

from deerflow.hoh import (
    Artifact,
    DevDoc,
    Evidence,
    EvidenceType,
    HohOrchestrator,
    InMemoryEvidenceStore,
    list_modules,
)


class StubPlanner:
    def __init__(self) -> None:
        self.calls = 0

    async def plan(self, module, spec, prior_evidence, current_artifact, iteration):
        self.calls += 1
        return DevDoc(
            module=module,
            iteration=iteration,
            scope=f"increment #{iteration}",
            acceptance=["artifact.version == expected"],
        )


class StubDeveloper:
    async def develop(self, current, spec, dev_doc):
        return Artifact(
            module=dev_doc.module,
            version=current.version + 1,
            payload={"note": dev_doc.scope},
        )


class StubQA:
    def __init__(self, fail_first: bool = False) -> None:
        self.fail_first = fail_first

    async def evaluate(self, candidate, spec, dev_doc, runtime_checks):
        evs = [
            Evidence(
                module=candidate.module,
                iteration=dev_doc.iteration,
                type=EvidenceType.VERIFIED,
                description=f"version {candidate.version} looks good",
            )
        ]
        if self.fail_first and dev_doc.iteration == 1:
            evs.append(
                Evidence(
                    module=candidate.module,
                    iteration=dev_doc.iteration,
                    type=EvidenceType.GAP,
                    description="still missing X",
                )
            )
        return evs


@pytest.mark.asyncio
async def test_orchestrator_runs_three_loops_and_persists_evidence():
    store = InMemoryEvidenceStore()
    orch = HohOrchestrator(
        planner=StubPlanner(),
        developer=StubDeveloper(),
        qa=StubQA(),
        evidence_store=store,
    )
    results = await orch.run(
        module="drama",
        spec="build a 60s short drama",
        initial_artifact=Artifact(module="drama", version=0),
        max_iterations=3,
    )
    assert len(results) == 3
    assert results[-1].artifact.version == 3
    all_ev = await store.list_for_module("drama")
    # one verified per loop
    assert len(all_ev) == 3


@pytest.mark.asyncio
async def test_orchestrator_respects_stop_when():
    store = InMemoryEvidenceStore()
    orch = HohOrchestrator(
        planner=StubPlanner(),
        developer=StubDeveloper(),
        qa=StubQA(fail_first=True),
        evidence_store=store,
    )

    def stop_when(evidence):
        return all(e.type == EvidenceType.VERIFIED for e in evidence)

    results = await orch.run(
        module="drama",
        spec="spec",
        initial_artifact=Artifact(module="drama", version=0),
        max_iterations=5,
        stop_when=stop_when,
    )
    # loop 1 has a GAP, loop 2 has only verified -> stop
    assert len(results) == 2
    assert results[-1].stopped_reason == "stop_when"


def test_module_loader_reads_builtin_drama_yaml():
    modules = list_modules()
    assert "drama" in modules
    spec = modules["drama"]
    assert spec.display_name == "短剧智能体"
    assert spec.developer_kind == "pipeline"
    assert len(spec.qa_blackbox) >= 3
