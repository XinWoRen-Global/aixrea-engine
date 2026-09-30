"""QA tester factory.

Maps module name -> QA tester instance. New modules register here
or in their own yaml (Phase 4 will auto-discover).
"""

from __future__ import annotations

from .qa_comic import ComicQATester
from .qa_drama import DramaQATester
from .qa_interactive import InteractiveQATester
from .qa_music import MusicQATester
from .qa_novel import NovelQATester
from .types import HohQATester

_REGISTRY: dict[str, HohQATester] = {
    "drama": DramaQATester(),
    "music": MusicQATester(),
    "comic": ComicQATester(),
    "novel": NovelQATester(),
    "interactive": InteractiveQATester(),
}


def get_qa_tester(module: str) -> HohQATester:
    """Return the QA tester for a module. Raises KeyError if unknown."""
    if module not in _REGISTRY:
        raise KeyError(f"No QA tester registered for module: {module}")
    return _REGISTRY[module]


def register_qa_tester(module: str, tester: HohQATester) -> None:
    """Runtime registration (for plugins / new modules)."""
    _REGISTRY[module] = tester
