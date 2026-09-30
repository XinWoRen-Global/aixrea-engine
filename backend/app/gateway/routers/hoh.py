"""HoH (Harness-of-Harness) admin API.

Endpoints:
  GET  /api/hoh/modules            list registered modules
  GET  /api/hoh/evidence/{module}   recent evidence for a module
  POST /api/hoh/run/{module}       trigger a dry-run loop (stub mode)

All endpoints require admin. This is an internal orchestration layer,
not a user-facing feature.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.gateway.deps import require_admin_user
from deerflow.hoh import (
    Artifact,
    DramaDeveloper,
    DramaQATester,
    HohOrchestrator,
    InMemoryEvidenceStore,
    LLMPlanner,
    list_modules,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/hoh", tags=["hoh"])


class RunRequest(BaseModel):
    spec: str = "dry-run spec"
    max_iterations: int = 1


class LoopResultOut(BaseModel):
    iteration: int
    stopped_reason: str | None
    evidence: list[dict[str, Any]]


@router.get("/modules")
async def list_registered_modules(_: dict = Depends(require_admin_user)):
    modules = list_modules()
    return {
        "modules": [
            {
                "name": spec.name,
                "display_name": spec.display_name,
                "developer_kind": spec.developer_kind,
                "cost_budget_per_loop_usd": spec.cost_budget_per_loop_usd,
            }
            for spec in modules.values()
        ]
    }


@router.get("/evidence/{module}")
async def list_evidence(
    module: str,
    limit: int = 50,
    _: dict = Depends(require_admin_user),
):
    # Phase 1: in-memory store only. Postgres store wired when engine ready.
    return {"module": module, "evidence": [], "note": "Postgres store not wired yet"}


@router.post("/run/{module}")
async def run_dry_run(
    module: str,
    body: RunRequest,
    _: dict = Depends(require_admin_user),
):
    if module != "drama":
        raise HTTPException(400, f"dry-run only supports 'drama' module for now, got {module}")

    async def stub_chat(_prompt: str) -> str:
        return '{"scope": "dry-run", "acceptance": ["no regression"], "preserve": []}'

    store = InMemoryEvidenceStore()
    orch = HohOrchestrator(
        planner=LLMPlanner(chat=stub_chat),
        developer=DramaDeveloper(),
        qa=DramaQATester(),
        evidence_store=store,
    )
    results = await orch.run(
        module=module,
        spec=body.spec,
        initial_artifact=Artifact(module=module, version=0),
        max_iterations=body.max_iterations,
    )
    return {
        "module": module,
        "loops": [
            LoopResultOut(
                iteration=r.iteration,
                stopped_reason=r.stopped_reason,
                evidence=[{"type": e.type.value, "description": e.description} for e in r.evidence],
            ).model_dump()
            for r in results
        ],
    }
