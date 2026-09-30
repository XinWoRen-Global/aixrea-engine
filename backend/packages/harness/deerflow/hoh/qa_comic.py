"""Comic QA rules.

Phase 2 skeleton. Focus: panel count, style consistency, text legibility.
"""

from __future__ import annotations

from typing import Any

from .types import Artifact, DevDoc, Evidence, EvidenceType

MIN_PANELS = 4
MIN_STYLE_CONSISTENCY = 0.85


class ComicQATester:
    async def evaluate(self, candidate: Artifact, spec: str, dev_doc: DevDoc, runtime_checks: dict[str, Any]) -> list[Evidence]:
        evs: list[Evidence] = []
        metric = candidate.payload.get("metric", {})
        i = dev_doc.iteration

        panels = metric.get("panel_count")
        if panels is None:
            evs.append(self._gap(candidate.module, i, "missing_panel_count"))
        elif int(panels) >= MIN_PANELS:
            evs.append(self._verified(candidate.module, i, f"panels_ok:{panels}"))
        else:
            evs.append(self._gap(candidate.module, i, f"panels_too_few:{panels}"))

        style = metric.get("style_consistency")
        if style is None:
            evs.append(self._gap(candidate.module, i, "missing_style_consistency"))
        elif float(style) >= MIN_STYLE_CONSISTENCY:
            evs.append(self._verified(candidate.module, i, f"style_ok:{style}"))
        else:
            evs.append(self._gap(candidate.module, i, f"style_low:{style}"))

        return evs

    @staticmethod
    def _verified(m, i, d):
        return Evidence(module=m, iteration=i, type=EvidenceType.VERIFIED, description=d)

    @staticmethod
    def _gap(m, i, d):
        return Evidence(module=m, iteration=i, type=EvidenceType.GAP, description=d)
