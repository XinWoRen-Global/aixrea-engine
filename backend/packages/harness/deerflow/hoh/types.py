"""HoH type definitions and protocols.

Per arXiv:2609.01481, each loop runs three invocations of the SAME
harness-model configuration, differing only by role prompt. We model
the roles as Protocols so existing Lead Agent / PipelineExecutor / tool
market executors can be wrapped with thin adapters without modification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

# ---------------------------------------------------------------------------
# Domain objects (cross-loop state)
# ---------------------------------------------------------------------------


class EvidenceType(StrEnum):
    """Classification of an evidence record."""

    VERIFIED = "verified"  # behavior confirmed working, must be preserved
    GAP = "gap"  # requirement not yet met
    REGRESSION = "regression"  # previously verified behavior now broken
    REOPENED = "reopened"  # a closed issue reappeared


@dataclass
class Evidence:
    """A single piece of evidence carried across HoH loops.

    Maps to the ``hoh_evidence`` table (migration added separately).
    """

    module: str
    iteration: int
    type: EvidenceType
    description: str
    artifact_ref: str | None = None
    metric: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None


@dataclass
class Artifact:
    """The evolving software artifact / work product.

    In Phase 0 this is an opaque bag of metadata. In later phases it
    will point at actual code refs, generated media, or DB rows.
    """

    module: str
    version: int
    payload: dict[str, Any] = field(default_factory=dict)
    notes: str = ""


@dataclass
class DevDoc:
    """Development document D_t produced by the Planner.

    Bounded but locally complete: one observable increment, with
    explicit acceptance conditions.
    """

    module: str
    iteration: int
    scope: str
    acceptance: list[str]
    preserve: list[str] = field(default_factory=list)
    estimated_cost_usd: float = 0.0


@dataclass
class LoopResult:
    """Outcome of one HoH loop."""

    module: str
    iteration: int
    dev_doc: DevDoc
    artifact: Artifact
    evidence: list[Evidence]
    stopped_reason: str | None = None


# ---------------------------------------------------------------------------
# Role protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class HohPlanner(Protocol):
    """Decides the next bounded increment. READ-ONLY on the artifact."""

    async def plan(
        self,
        module: str,
        spec: str,
        prior_evidence: list[Evidence],
        current_artifact: Artifact,
        iteration: int,
    ) -> DevDoc: ...


@runtime_checkable
class HohDeveloper(Protocol):
    """Implements the increment. SINGLE WRITER on the artifact."""

    async def develop(self, current: Artifact, spec: str, dev_doc: DevDoc) -> Artifact: ...


@runtime_checkable
class HohQATester(Protocol):
    """Independently evaluates a frozen candidate. READ-ONLY."""

    async def evaluate(
        self,
        candidate: Artifact,
        spec: str,
        dev_doc: DevDoc,
        runtime_checks: dict[str, Any],
    ) -> list[Evidence]: ...


# ---------------------------------------------------------------------------
# Module spec (loaded from yaml)
# ---------------------------------------------------------------------------


@dataclass
class HoHModuleSpec:
    """Declarative description of a module eligible for HoH scheduling."""

    name: str
    display_name: str
    developer_kind: str  # "lead_agent" | "pipeline" | "tool_market"
    entry: str  # import path, e.g. "deerflow.agents:make_lead_agent"
    tools_allowlist: list[str] = field(default_factory=list)
    qa_blackbox: list[dict[str, Any]] = field(default_factory=list)
    qa_whitebox: list[dict[str, Any]] = field(default_factory=list)
    evidence_ttl_days: int = 30
    cost_budget_per_loop_usd: float = 0.50
    enabled: bool = True
