"""Music QA rules.

Phase 2 skeleton. Real thresholds to be tuned against production data.
"""

from __future__ import annotations

from typing import Any

from .types import Artifact, DevDoc, Evidence, EvidenceType

DURATION_MIN = 15
DURATION_MAX = 300


class MusicQATester:
    async def evaluate(self, candidate: Artifact, spec: str, dev_doc: DevDoc, runtime_checks: dict[str, Any]) -> list[Evidence]:
        evs: list[Evidence] = []
        metric = candidate.payload.get("metric", {})
        iter_ = dev_doc.iteration

        duration = metric.get("duration")
        if duration is None:
            evs.append(self._gap(candidate.module, iter_, "missing_duration"))
        elif DURATION_MIN <= float(duration) <= DURATION_MAX:
            evs.append(self._verified(candidate.module, iter_, f"duration_ok:{duration}"))
        else:
            evs.append(self._gap(candidate.module, iter_, f"duration_out_of_range:{duration}"))

        cr = metric.get("copyright_score")
        if cr is None:
            evs.append(self._gap(candidate.module, iter_, "missing_copyright"))
        elif float(cr) >= 0.9:
            evs.append(self._verified(candidate.module, iter_, f"copyright_ok:{cr}"))
        else:
            evs.append(self._gap(candidate.module, iter_, f"copyright_low:{cr}"))

        return evs

    @staticmethod
    def _verified(m, i, desc):
        return Evidence(module=m, iteration=i, type=EvidenceType.VERIFIED, description=desc)

    @staticmethod
    def _gap(m, i, desc):
        return Evidence(module=m, iteration=i, type=EvidenceType.GAP, description=desc)
