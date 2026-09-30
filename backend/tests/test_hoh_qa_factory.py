"""QA factory + template loader tests."""

from __future__ import annotations

import pytest

from deerflow.hoh import (
    DramaQATester,
    MusicQATester,
    get_qa_tester,
    list_modules,
    register_qa_tester,
)


def test_factory_returns_registered_testers():
    assert isinstance(get_qa_tester("drama"), DramaQATester)
    assert isinstance(get_qa_tester("music"), MusicQATester)


def test_factory_unknown_module_raises():
    with pytest.raises(KeyError):
        get_qa_tester("nonexistent_module_xyz")


def test_factory_register_runtime_tester():
    class FakeQA:
        async def evaluate(self, *args, **kw):
            return []

    register_qa_tester("fake_module", FakeQA())
    assert isinstance(get_qa_tester("fake_module"), FakeQA)


def test_module_loader_skips_template_and_disabled():
    modules = list_modules()
    # _template.yaml starts with underscore; list_modules only picks *.yaml
    # but the template has enabled: false so it must not appear
    assert "_template" not in modules
    assert "drama" in modules
    assert "interactive" in modules
