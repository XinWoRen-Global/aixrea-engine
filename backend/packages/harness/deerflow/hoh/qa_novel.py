"""Novel QA rules.

Phase 2 skeleton. Focus: chapter length, coherence, style consistency.
"""

from __future__ import annotations

from typing import Any

from .types import Artifact, DevDoc, Evidence, EvidenceType

MIN_CHAPTER_WORDS = 800
MIN_COHERENCE = 0.8


class NovelQATester:
    async def evaluate(self, candidate: Artifact, spec: str, dev_doc: DevDoc, runtime_checks: dict[str, Any]) -> list[Evidence]:
        evs: list[Evidence] = []
        metric = candidate.payload.get("metric", {})
        i = dev_doc.iteration

        words = metric.get("word_count")
        if words is None:
            evs.append(self._gap(candidate.module, i, "missing_word_count"))
        elif int(words) >= MIN_CHAPTER_WORDS:
            evs.append(self._verified(candidate.module, i, f"words_ok:{words}"))
        else:
            evs.append(self._gap(candidate.module, i, f"words_too_few:{words}"))

        coherence = metric.get("coherence")
        if coherence is None:
            evs.append(self._gap(candidate.module, i, "missing_coherence"))
        elif float(coherence) >= MIN_COHERENCE:
            evs.append(self._verified(candidate.module, i, f"coherence_ok:{coherence}"))
        else:
            evs.append(self._gap(candidate.module, i, f"coherence_low:{coherence}"))

        return evs

    @staticmethod
    def _verified(m, i, d):
        return Evidence(module=m, iteration=i, type=EvidenceType.VERIFIED, description=d)

    @staticmethod
    def _gap(m, i, d):
        return Evidence(module=m, iteration=i, type=EvidenceType.GAP, description=d)
