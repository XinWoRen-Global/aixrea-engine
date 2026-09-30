"""Harness-of-Harness (HoH) outer orchestrator.

Design doc: devops/docs/hoh-orchestrator-design-v1.md
            devops/docs/hoh-orchestrator-design-v1.1-extension.md

This package implements the outer meta-harness that wraps existing
inner harnesses (Lead Agent, PipelineExecutor, tools market). It does
NOT replace them.

Roles per loop:
  - ProjectPlanner  : pick a bounded increment (read-only)
  - Developer       : implement the increment (single writer)
  - QATester        : independently evaluate a frozen candidate (read-only)
  - Learn           : persist evidence into the evidence store

Phase 0 (this commit): skeleton only.
  - types / protocols
  - orchestrator loop
  - in-memory evidence store (DB migration is a separate step)
  - module yaml loader
No production wiring yet.
"""

from .chat_signals import ChatSignal, signals_to_evidence
from .drama_developer import DramaDeveloper
from .evidence import EvidenceStore, InMemoryEvidenceStore
from .llm_planner import LLMPlanner
from .module_loader import list_modules, load_module
from .orchestrator import HohOrchestrator
from .qa_comic import ComicQATester
from .qa_drama import DramaQATester
from .qa_factory import get_qa_tester, register_qa_tester
from .qa_interactive import InteractiveQATester
from .qa_music import MusicQATester
from .qa_novel import NovelQATester
from .tool_ranking import ToolSignal, rank_tools
from .types import (
    Artifact,
    DevDoc,
    Evidence,
    EvidenceType,
    HohDeveloper,
    HoHModuleSpec,
    HohPlanner,
    HohQATester,
    LoopResult,
)

__all__ = [
    "Artifact",
    "DevDoc",
    "Evidence",
    "EvidenceType",
    "HoHModuleSpec",
    "HohDeveloper",
    "HohQATester",
    "HohPlanner",
    "LoopResult",
    "HohOrchestrator",
    "InMemoryEvidenceStore",
    "EvidenceStore",
    "load_module",
    "list_modules",
    "DramaDeveloper",
    "DramaQATester",
    "MusicQATester",
    "ComicQATester",
    "NovelQATester",
    "InteractiveQATester",
    "get_qa_tester",
    "register_qa_tester",
    "LLMPlanner",
    "ChatSignal",
    "ToolSignal",
    "rank_tools",
    "signals_to_evidence",
]
