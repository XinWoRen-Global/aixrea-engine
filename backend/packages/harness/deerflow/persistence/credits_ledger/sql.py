"""SQLAlchemy-backed credits ledger store (async).

Each method acquires its own short-lived session from the shared factory
(see :mod:`deerflow.persistence.engine`). The store implements the
hold/commit/release state machine and hold idempotency; the balance side
effects are the caller's concern (the gateway service wires them).

Concurrency: SQLite serialises writes per file (WAL + busy_timeout), Postgres
uses row-level locking. Idempotency is guaranteed by the unique ``hold_id``
index regardless of backend: a concurrent duplicate ``hold`` insert loses the
UNIQUE race and is re-fetched as the existing row.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from deerflow.persistence.credits_ledger.model import (
    STATUS_COMMITTED,
    STATUS_HELD,
    STATUS_RELEASED,
    CreditLedgerRow,
)

logger = logging.getLogger(__name__)


class CreditLedgerStateError(Exception):
    """Raised when a hold transition is illegal for the current state."""


class CreditLedgerRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    # ── Serialization helpers ──────────────────────────────────────────

    @staticmethod
    def _row_to_dict(row: CreditLedgerRow, *, exclude: set[str] | None = None) -> dict:
        d = row.to_dict(exclude=exclude)
        for key in ("created_at", "updated_at", "committed_at", "released_at", "expires_at"):
            val = d.get(key)
            if isinstance(val, datetime):
                # SQLite drops tzinfo on read; normalize so output is tz-aware.
                d[key] = val.replace(tzinfo=UTC).isoformat() if val.tzinfo is None else val.isoformat()
        return d

    # ── Reads ─────────────────────────────────────────────────────────

    async def get_by_hold_id(self, hold_id: str) -> dict | None:
        """Fetch a hold by its idempotency key, or None."""
        stmt = select(CreditLedgerRow).where(CreditLedgerRow.hold_id == hold_id)
        async with self._sf() as session:
            row = (await session.execute(stmt)).scalar_one_or_none()
            return self._row_to_dict(row) if row is not None else None

    async def get_by_id(self, ledger_id: str) -> dict | None:
        stmt = select(CreditLedgerRow).where(CreditLedgerRow.id == ledger_id)
        async with self._sf() as session:
            row = (await session.execute(stmt)).scalar_one_or_none()
            return self._row_to_dict(row) if row is not None else None

    async def list_by_user(
        self,
        user_id: str,
        *,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        stmt = select(CreditLedgerRow).where(CreditLedgerRow.user_id == user_id)
        if status is not None:
            stmt = stmt.where(CreditLedgerRow.status == status)
        stmt = stmt.order_by(CreditLedgerRow.created_at.desc()).limit(limit).offset(offset)
        async with self._sf() as session:
            rows = (await session.execute(stmt)).scalars().all()
            return [self._row_to_dict(r) for r in rows]

    async def count_by_scope(self, scope: str, scope_id: str, *, status: str | None = None) -> int:
        """Count holds for a business scope (e.g. an album) — used to avoid
        double-charging when a pipeline is re-executed."""
        stmt = select(func.count(CreditLedgerRow.id)).where(
            CreditLedgerRow.scope == scope,
            CreditLedgerRow.scope_id == scope_id,
        )
        if status is not None:
            stmt = stmt.where(CreditLedgerRow.status == status)
        async with self._sf() as session:
            return int((await session.execute(stmt)).scalar_one() or 0)

    async def list_expired_held(self, *, before: datetime, limit: int = 500) -> list[dict]:
        """Holds still in ``held`` whose deadline passed — candidates for the
        auto-release sweeper (crash / lost-worker protection)."""
        stmt = select(CreditLedgerRow).where(CreditLedgerRow.status == STATUS_HELD, CreditLedgerRow.expires_at.is_not(None)).where(CreditLedgerRow.expires_at < before).order_by(CreditLedgerRow.expires_at.asc()).limit(limit)
        async with self._sf() as session:
            rows = (await session.execute(stmt)).scalars().all()
            return [self._row_to_dict(r) for r in rows]

    # ── State machine ────────────────────────────────────────────────

    async def create_hold(
        self,
        *,
        hold_id: str,
        user_id: str,
        amount: int,
        scope: str,
        kind: str,
        org_id: str | None = None,
        scope_id: str | None = None,
        reason: str | None = None,
        meta: dict[str, Any] | None = None,
        expires_at: datetime | None = None,
    ) -> dict:
        """Insert a new ``held`` row.

        Idempotent: if ``hold_id`` already exists, the original row is
        returned untouched — a concurrent duplicate (or a caller retry) can
        never double-charge.
        """
        import uuid

        now = datetime.now(UTC)
        row = CreditLedgerRow(
            id=uuid.uuid4().hex,
            hold_id=hold_id,
            user_id=user_id,
            org_id=org_id,
            scope=scope,
            scope_id=scope_id,
            kind=kind,
            amount=max(0, int(amount)),
            status=STATUS_HELD,
            reason=reason,
            meta=meta or {},
            expires_at=expires_at,
            created_at=now,
            updated_at=now,
        )
        try:
            async with self._sf() as session:
                session.add(row)
                await session.commit()
                await session.refresh(row)
                return self._row_to_dict(row)
        except IntegrityError:
            # Unique(hold_id) race / retry → return the existing hold untouched.
            async with self._sf() as session:
                await session.rollback()
                existing = (await session.execute(select(CreditLedgerRow).where(CreditLedgerRow.hold_id == hold_id))).scalar_one_or_none()
            if existing is None:
                raise
            return self._row_to_dict(existing)

    async def _transition(self, hold_id: str, target: str) -> dict | None:
        """Transition a held row to *target*, only if it is currently ``held``.

        Uses a conditional UPDATE so concurrent committers/releasers race
        safely: exactly one wins the transition; losers see the row in its
        current (possibly terminal) state. Returns the row dict after the
        update, or None when the hold does not exist.
        """
        target_col = {STATUS_COMMITTED: "committed_at", STATUS_RELEASED: "released_at"}[target]
        now = datetime.now(UTC)
        stmt = (
            update(CreditLedgerRow)
            .where(CreditLedgerRow.hold_id == hold_id, CreditLedgerRow.status == STATUS_HELD)
            .values(
                status=target,
                updated_at=now,
                **{target_col: now},
            )
        )
        async with self._sf() as session:
            result = await session.execute(stmt)
            await session.commit()
        if result.rowcount == 0:
            # No held row matched: either missing or already terminal. Fetch
            # and return as-is so the caller can reconcile idempotently.
            return await self.get_by_hold_id(hold_id)
        async with self._sf() as session:
            row = (await session.execute(select(CreditLedgerRow).where(CreditLedgerRow.hold_id == hold_id))).scalar_one()
            return self._row_to_dict(row)

    async def commit_hold(self, hold_id: str) -> dict | None:
        """Mark a held transaction as committed (credits consumed)."""
        return await self._transition(hold_id, STATUS_COMMITTED)

    async def release_hold(self, hold_id: str) -> dict | None:
        """Mark a held transaction as released (credits refunded)."""
        return await self._transition(hold_id, STATUS_RELEASED)
