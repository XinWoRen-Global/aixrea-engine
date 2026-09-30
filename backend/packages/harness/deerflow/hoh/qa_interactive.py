"""Interactive film / game QA rules.

Phase 2 skeleton. Focus: branch reachability, ending count, playability.
"""

from __future__ import annotations

from typing import Any

from .types import Artifact, DevDoc, Evidence, EvidenceType

MIN_BRANCHES = 3
MIN_ENDINGS = 2


class InteractiveQATester:
    async def evaluate(self, candidate: Artifact, spec: str, dev_doc: DevDoc, runtime_checks: dict[str, Any]) -> list[Evidence]:
        evs: list[Evidence] = []
        metric = candidate.payload.get("metric", {})
        i = dev_doc.iteration

        branches = metric.get("branch_count")
        if branches is None:
            evs.append(self._gap(candidate.module, i, "missing_branch_count"))
        elif int(branches) >= MIN_BRANCHES:
            evs.append(self._verified(candidate.module, i, f"branches_ok:{branches}"))
        else:
            evs.append(self._gap(candidate.module, i, f"branches_too_few:{branches}"))

        endings = metric.get("ending_count")
        if endings is None:
            evs.append(self._gap(candidate.module, i, "missing_ending_count"))
        elif int(endings) >= MIN_ENDINGS:
            evs.append(self._verified(candidate.module, i, f"endings_ok:{endings}"))
        else:
            evs.append(self._gap(candidate.module, i, f"endings_too_few:{endings}"))

        playable = metric.get("playable")
        if playable is True:
            evs.append(self._verified(candidate.module, i, "playable:true"))
        else:
            evs.append(self._gap(candidate.module, i, f"not_playable:{playable}"))

        return evs

    @staticmethod
    def _verified(m, i, d):
        return Evidence(module=m, iteration=i, type=EvidenceType.VERIFIED, description=d)

    @staticmethod
    def _gap(m, i, d):
        return Evidence(module=m, iteration=i, type=EvidenceType.GAP, description=d)
