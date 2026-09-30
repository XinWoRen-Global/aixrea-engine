"""merge 0004_campaigns and 0004_run_ownership

Revision ID: 0004_merge
Revises: 0004_campaigns, 0004_run_ownership
Create Date: 2026-07-30
"""

from collections.abc import Sequence

revision: str = "0004_merge"
down_revision: str | Sequence[str] | None = ("0004_campaigns", "0004_run_ownership")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
