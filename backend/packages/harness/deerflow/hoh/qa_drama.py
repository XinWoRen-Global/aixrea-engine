"""Drama (short film) QA rules.

Pure black-box / white-box checks. No LLM, no network. These run
against a frozen Artifact produced by the drama pipeline.

Phase 1: minimal rules from modules/drama.yaml. Later phases add
LLM-as-judge for aesthetic quality.
"""

from __future__ import annotations

from typing import Any

from .types import Artifact, DevDoc, Evidence, EvidenceType

DURATION_MIN = 60
DURATION_MAX = 180
SUBTITLE_SYNC_MIN = 0.9
COPYRIGHT_SCORE_MIN = 0.9


class DramaQATester:
    """Independent QA for the drama module.

    Follows HoH contract: read-only on candidate, no mutation.
    """

    async def evaluate(
        self,
        candidate: Artifact,
        spec: str,
        dev_doc: DevDoc,
        runtime_checks: dict[str, Any],
    ) -> list[Evidence]:
        evs: list[Evidence] = []
        metric: dict[str, Any] = candidate.payload.get("metric", {})
        iteration = dev_doc.iteration
        module = candidate.module

        # Black-box: duration
        duration = metric.get("duration")
        if duration is None:
            evs.append(self._gap(module, iteration, "missing_duration", candidate))
        elif DURATION_MIN <= float(duration) <= DURATION_MAX:
            evs.append(self._verified(module, iteration, f"duration_ok:{duration}", candidate, {"duration": duration}))
        else:
            evs.append(self._gap(module, iteration, f"duration_out_of_range:{duration}", candidate, {"duration": duration}))

        # Black-box: subtitle sync
        sync = metric.get("subtitle_sync")
        if sync is None:
            evs.append(self._gap(module, iteration, "missing_subtitle_sync", candidate))
        elif float(sync) >= SUBTITLE_SYNC_MIN:
            evs.append(self._verified(module, iteration, f"subtitle_sync_ok:{sync}", candidate, {"subtitle_sync": sync}))
        else:
            evs.append(self._gap(module, iteration, f"subtitle_sync_low:{sync}", candidate, {"subtitle_sync": sync}))

        # Black-box: copyright score
        cr = metric.get("copyright_score")
        if cr is None:
            evs.append(self._gap(module, iteration, "missing_copyright_score", candidate))
        elif float(cr) >= COPYRIGHT_SCORE_MIN:
            evs.append(self._verified(module, iteration, f"copyright_ok:{cr}", candidate, {"copyright_score": cr}))
        else:
            evs.append(self._gap(module, iteration, f"copyright_low:{cr}", candidate, {"copyright_score": cr}))

        # White-box: render log schema
        render_log = candidate.payload.get("render_log")
        if isinstance(render_log, dict) and render_log.get("schema_version") == "v1":
            evs.append(self._verified(module, iteration, "render_log_schema_ok", candidate))
        else:
            evs.append(self._gap(module, iteration, "render_log_schema_missing", candidate))

        return evs

    @staticmethod
    def _verified(module, iteration, desc, artifact, metric=None) -> Evidence:
        return Evidence(
            module=module,
            iteration=iteration,
            type=EvidenceType.VERIFIED,
            description=desc,
            artifact_ref=artifact.notes or None,
            metric=metric or {},
        )

    @staticmethod
    def _gap(module, iteration, desc, artifact, metric=None) -> Evidence:
        return Evidence(
            module=module,
            iteration=iteration,
            type=EvidenceType.GAP,
            description=desc,
            artifact_ref=artifact.notes or None,
            metric=metric or {},
        )
