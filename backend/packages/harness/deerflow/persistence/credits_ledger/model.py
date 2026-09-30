"""ORM model for the credits ledger — transactional hold/commit/release records.

One row per held transaction (the ``hold``). The row records the intent to
spend *amount* credits on behalf of *user_id*, and walks a strict state
machine:

    held → committed   (operation succeeded, credits consumed)
    held → released    (operation failed / cancelled / expired, credits refunded)

``hold_id`` is the caller-supplied idempotency key: creating a hold with an
existing ``hold_id`` is a no-op that returns the original row, so retries and
duplicate submissions can never double-charge. This is the audit + state
machine layer only — the actual balance lives in the billing store (InsForge
``user_memberships``), which the service layer mutates through a pluggable
hook when it transitions a hold.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.persistence.base import Base

# Lifecycle states. Exported for the service + routers to reuse without
# importing this ORM module.
STATUS_HELD = "held"
STATUS_COMMITTED = "committed"
STATUS_RELEASED = "released"

# Terminal states: a hold in one of these must never be transitioned again.
TERMINAL_STATUSES = frozenset({STATUS_COMMITTED, STATUS_RELEASED})

# Valid transitions: held -> committed | released.
VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    STATUS_HELD: frozenset({STATUS_COMMITTED, STATUS_RELEASED}),
}


class CreditLedgerRow(Base):
    __tablename__ = "credits_ledger"
    __table_args__ = (
        # Hold idempotency: unique per hold so a replayed hold() returns the
        # original row instead of double-charging.
        Index("uq_credits_ledger_hold_id", "hold_id", unique=True),
        # Sweeper scan: expired holds still in "held" state, oldest first.
        Index("ix_credits_ledger_status_expires", "status", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # Caller-supplied idempotency key (natural key of the hold lifecycle).
    hold_id: Mapped[str] = mapped_column(String(128))
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    org_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    # Business scope: "album", "node", "skill_run", "chat", "video", ...
    scope: Mapped[str] = mapped_column(String(32))
    scope_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    # Billing kind, e.g. "drama_episode", "video_generation".
    kind: Mapped[str] = mapped_column(String(64))
    # Credits held. Positive integer.
    amount: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default=STATUS_HELD, index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Extra audit payload. Named ``meta`` (DB column ``metadata`` would collide
    # with SQLAlchemy's reserved Declarative attribute name).
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    # Hold deadline. The sweeper auto-releases any hold still in "held" after
    # this timestamp (crash / lost worker protection).
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
