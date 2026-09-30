"""Drama QA tests.

Verifies the pure-rule checks from modules/drama.yaml:
duration, subtitle sync, copyright score, render log schema.
"""

from __future__ import annotations

import pytest

from deerflow.hoh import Artifact, DevDoc
from deerflow.hoh.qa_drama import DramaQATester
from deerflow.hoh.types import EvidenceType


def _doc(iteration: int = 1) -> DevDoc:
    return DevDoc(module="drama", iteration=iteration, scope="t", acceptance=[])


@pytest.mark.asyncio
async def test_drama_qa_flags_all_gaps_when_metric_missing():
    qa = DramaQATester()
    art = Artifact(module="drama", version=1, payload={})
    evs = await qa.evaluate(art, "spec", _doc(), {})
    types = [e.type for e in evs]
    assert types.count(EvidenceType.GAP) == 4
    assert types.count(EvidenceType.VERIFIED) == 0


@pytest.mark.asyncio
async def test_drama_qa_accepts_valid_candidate():
    qa = DramaQATester()
    art = Artifact(
        module="drama",
        version=1,
        payload={
            "metric": {
                "duration": 90,
                "subtitle_sync": 0.95,
                "copyright_score": 0.95,
            },
            "render_log": {"schema_version": "v1", "nodes_completed": 8},
        },
    )
    evs = await qa.evaluate(art, "spec", _doc(), {})
    types = [e.type for e in evs]
    assert types.count(EvidenceType.VERIFIED) == 4
    assert types.count(EvidenceType.GAP) == 0


@pytest.mark.asyncio
async def test_drama_qa_flags_out_of_range_duration():
    qa = DramaQATester()
    art = Artifact(
        module="drama",
        version=1,
        payload={
            "metric": {"duration": 30, "subtitle_sync": 0.95, "copyright_score": 0.95},
            "render_log": {"schema_version": "v1"},
        },
    )
    evs = await qa.evaluate(art, "spec", _doc(), {})
    dur_ev = next(e for e in evs if "duration" in e.description)
    assert dur_ev.type == EvidenceType.GAP
