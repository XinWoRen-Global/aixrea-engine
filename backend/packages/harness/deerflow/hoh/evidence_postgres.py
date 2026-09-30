"""Postgres-backed evidence store.

Uses the shared SQLAlchemy async session factory. If no engine is
configured (e.g. unit tests), callers fall back to InMemoryEvidenceStore.

Tables: migrations/20260915_create_hoh_tables.sql
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .types import Evidence, EvidenceType

logger = logging.getLogger(__name__)


class PostgresEvidenceStore:
    """Persist HoH evidence in Postgres."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, ev: Evidence) -> None:
        await self._session.execute(
            text(
                """
                INSERT INTO hoh_evidence
                    (id, module, iteration, type, description, artifact_ref, metric, created_at, expires_at)
                VALUES
                    (:id, :module, :iteration, :type, :description, :artifact_ref, CAST(:metric AS JSONB), :created_at, :expires_at)
                """
            ),
            {
                "id": ev.id,
                "module": ev.module,
                "iteration": ev.iteration,
                "type": ev.type.value,
                "description": ev.description,
                "artifact_ref": ev.artifact_ref,
                "metric": __import__("json").dumps(ev.metric),
                "created_at": ev.created_at,
                "expires_at": ev.expires_at,
            },
        )

    async def list_for_module(self, module: str, limit: int = 100) -> list[Evidence]:
        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT id, module, iteration, type, description, artifact_ref,
                           metric, created_at, expires_at
                    FROM hoh_evidence
                    WHERE module = :module
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """
                ),
                {"module": module, "limit": limit},
            )
        ).all()
        return [self._row_to_evidence(r) for r in rows]

    async def recent(self, module: str, since_iteration: int) -> list[Evidence]:
        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT id, module, iteration, type, description, artifact_ref,
                           metric, created_at, expires_at
                    FROM hoh_evidence
                    WHERE module = :module AND iteration > :since
                    ORDER BY created_at ASC
                    """
                ),
                {"module": module, "since": since_iteration},
            )
        ).all()
        return [self._row_to_evidence(r) for r in rows]

    @staticmethod
    def _row_to_evidence(row) -> Evidence:
        import json

        metric_raw = row.metric if isinstance(row.metric, dict) else json.loads(row.metric or "{}")
        return Evidence(
            id=str(row.id),
            module=row.module,
            iteration=row.iteration,
            type=EvidenceType(row.type),
            description=row.description,
            artifact_ref=row.artifact_ref,
            metric=metric_raw,
            created_at=row.created_at,
            expires_at=row.expires_at,
        )
