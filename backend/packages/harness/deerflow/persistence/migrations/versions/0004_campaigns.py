"""campaigns -- multi-tenant production campaign store.

Revision ID: 0004_campaigns
Revises: 0003_scheduled_tasks
Create Date: 2026-07-11

Adds the ``campaigns`` table used by the pipeline-orchestrator skill. Every
row is owned by a single tenant via ``owner_user_id``; the execute endpoint
filters all reads/writes by it so campaigns are strictly isolated per user.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_campaigns"
down_revision: str | Sequence[str] | None = "0003_scheduled_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "campaigns",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("source_campaign_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("campaigns", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_campaigns_owner_user_id"), ["owner_user_id"], unique=False)
        batch_op.create_index("ix_campaigns_owner_created", ["owner_user_id", "created_at"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("campaigns", schema=None) as batch_op:
        batch_op.drop_index("ix_campaigns_owner_created")
        batch_op.drop_index(batch_op.f("ix_campaigns_owner_user_id"))

    op.drop_table("campaigns")
