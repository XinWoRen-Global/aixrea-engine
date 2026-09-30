"""Evidence store.

Phase 0 ships an in-memory implementation so the orchestrator loop
can be exercised in tests. The Postgres-backed implementation will
follow the migration in a later commit.
"""

from __future__ import annotations

from typing import Protocol

from .types import Evidence


class EvidenceStore(Protocol):
    async def append(self, ev: Evidence) -> None: ...
    async def list_for_module(self, module: str, limit: int = 100) -> list[Evidence]: ...
    async def recent(self, module: str, since_iteration: int) -> list[Evidence]: ...


class InMemoryEvidenceStore:
    """Process-local evidence store. For tests and dry-run only."""

    def __init__(self) -> None:
        self._items: list[Evidence] = []

    async def append(self, ev: Evidence) -> None:
        self._items.append(ev)

    async def list_for_module(self, module: str, limit: int = 100) -> list[Evidence]:
        items = [e for e in self._items if e.module == module]
        items.sort(key=lambda e: e.created_at, reverse=True)
        return items[:limit]

    async def recent(self, module: str, since_iteration: int) -> list[Evidence]:
        return [e for e in self._items if e.module == module and e.iteration > since_iteration]
