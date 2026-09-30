"""QA smoke tests for the four remaining creation pipelines."""

from __future__ import annotations

import pytest

from deerflow.hoh import Artifact, DevDoc
from deerflow.hoh.qa_comic import ComicQATester
from deerflow.hoh.qa_interactive import InteractiveQATester
from deerflow.hoh.qa_music import MusicQATester
from deerflow.hoh.qa_novel import NovelQATester
from deerflow.hoh.types import EvidenceType


def _doc(iter_=1):
    return DevDoc(module="test", iteration=iter_, scope="t", acceptance=[])


@pytest.mark.asyncio
async def test_music_qa_accepts_valid():
    art = Artifact(module="music", version=1, payload={"metric": {"duration": 60, "copyright_score": 0.95}})
    evs = await MusicQATester().evaluate(art, "s", _doc(), {})
    assert all(e.type == EvidenceType.VERIFIED for e in evs)


@pytest.mark.asyncio
async def test_comic_qa_flags_too_few_panels():
    art = Artifact(module="comic", version=1, payload={"metric": {"panel_count": 2, "style_consistency": 0.9}})
    evs = await ComicQATester().evaluate(art, "s", _doc(), {})
    assert any(e.type == EvidenceType.GAP and "panels" in e.description for e in evs)


@pytest.mark.asyncio
async def test_novel_qa_flags_low_coherence():
    art = Artifact(module="novel", version=1, payload={"metric": {"word_count": 2000, "coherence": 0.5}})
    evs = await NovelQATester().evaluate(art, "s", _doc(), {})
    assert any(e.type == EvidenceType.GAP and "coherence" in e.description for e in evs)


@pytest.mark.asyncio
async def test_interactive_qa_requires_playable():
    art = Artifact(module="interactive", version=1, payload={"metric": {"branch_count": 5, "ending_count": 3, "playable": False}})
    evs = await InteractiveQATester().evaluate(art, "s", _doc(), {})
    assert any(e.type == EvidenceType.GAP and "not_playable" in e.description for e in evs)
