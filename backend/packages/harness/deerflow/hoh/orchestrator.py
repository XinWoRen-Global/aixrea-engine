"""HoH orchestrator: the outer meta-harness loop.

Per arXiv:2609.01481, one loop is:

    D_t   = Planner(S, E_{t-1}; read_only(A_{t-1}))
    A_t   = Developer(A_{t-1}; S, D_t)
    E_t   = QA(read_only(A_t); S, D_t, Runtime.check(A_t))

Phase 0: synchronous skeleton. Real adapters (Lead Agent, Pipeline,
tool market) plug in via the HohPlanner / HohDeveloper / HohQATester
protocols. No business wiring yet.
"""

from __future__ import annotations

from .evidence import EvidenceStore
from .types import (
    Artifact,
    HohDeveloper,
    HohPlanner,
    HohQATester,
    LoopResult,
)


class HohOrchestrator:
    """Runs the planning -> development -> QA loop for one module."""

    def __init__(
        self,
        planner: HohPlanner,
        developer: HohDeveloper,
        qa: HohQATester,
        evidence_store: EvidenceStore,
    ) -> None:
        self.planner = planner
        self.developer = developer
        self.qa = qa
        self.store = evidence_store

    async def run(
        self,
        module: str,
        spec: str,
        initial_artifact: Artifact,
        max_iterations: int = 10,
        stop_when: callable | None = None,
    ) -> list[LoopResult]:
        """Run HoH loops until budget exhausted or stop_when returns True.

        stop_when(recent_evidence) -> bool lets the caller short-circuit
        (e.g. "all acceptance criteria met" or "cost exceeded").
        """
        results: list[LoopResult] = []
        artifact = initial_artifact

        for t in range(1, max_iterations + 1):
            prior = await self.store.list_for_module(module, limit=50)

            # 1. Plan (read-only on artifact)
            dev_doc = await self.planner.plan(
                module=module,
                spec=spec,
                prior_evidence=prior,
                current_artifact=artifact,
                iteration=t,
            )

            # 2. Develop (single writer)
            new_artifact = await self.developer.develop(
                current=artifact,
                spec=spec,
                dev_doc=dev_doc,
            )

            # 3. QA (read-only on new artifact)
            runtime_checks: dict[str, object] = {"frozen": True, "iteration": t}
            evidence = await self.qa.evaluate(
                candidate=new_artifact,
                spec=spec,
                dev_doc=dev_doc,
                runtime_checks=runtime_checks,
            )

            # 4. Persist evidence
            for ev in evidence:
                await self.store.append(ev)

            result = LoopResult(
                module=module,
                iteration=t,
                dev_doc=dev_doc,
                artifact=new_artifact,
                evidence=evidence,
            )
            results.append(result)

            artifact = new_artifact

            if stop_when is not None and stop_when(evidence):
                result.stopped_reason = "stop_when"
                break

        return results
