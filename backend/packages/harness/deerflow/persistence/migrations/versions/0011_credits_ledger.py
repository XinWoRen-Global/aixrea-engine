"""credits_ledger.

Revision ID: 0011_credits_ledger
Revises: 0010_run_cancel_request
Create Date: 2026-08-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_credits_ledger"
down_revision: str | Sequence[str] | None = "0010_run_cancel_request"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("credits_ledger"):
        # Idempotent: a DB whose full-metadata create_all already provisioned
        # the table (e.g. legacy test seeds) must not have it re-created here.
        return
    op.create_table(
        "credits_ledger",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("hold_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("org_id", sa.String(length=64), nullable=True),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("scope_id", sa.String(length=128), nullable=True),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.Index("uq_credits_ledger_hold_id", "hold_id", unique=True),
        sa.Index("ix_credits_ledger_status_expires", "status", "expires_at"),
    )
    with op.batch_alter_table("credits_ledger", schema=None) as batch_op:
        batch_op.create_index("ix_credits_ledger_user_id", ["user_id"], unique=False)
        batch_op.create_index("ix_credits_ledger_org_id", ["org_id"], unique=False)
        batch_op.create_index("ix_credits_ledger_scope_id", ["scope_id"], unique=False)
        batch_op.create_index("ix_credits_ledger_status", ["status"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("credits_ledger", schema=None) as batch_op:
        batch_op.drop_index("ix_credits_ledger_user_id")
        batch_op.drop_index("ix_credits_ledger_org_id")
        batch_op.drop_index("ix_credits_ledger_scope_id")
        batch_op.drop_index("ix_credits_ledger_status")
    op.drop_table("credits_ledger")
