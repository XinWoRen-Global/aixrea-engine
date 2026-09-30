"""ORM model for production campaigns (pipeline-orchestrator output).

Campaigns are multi-tenant: every row carries ``owner_user_id`` and ALL
reads/writes are scoped by it, so one tenant can never see or mutate
another tenant's campaigns. This closes the cross-tenant-leak / IDOR gap
that existed while the frontend proxied ``user_id`` but the backend had no
campaign store to filter on.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, String, text
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.persistence.base import Base


class CampaignRow(Base):
    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    channel: Mapped[str | None] = mapped_column(String(32))
    # "draft" | "running" | "completed" | "failed"
    status: Mapped[str] = mapped_column(String(20), default="draft")
    config_json: Mapped[dict] = mapped_column(JSON, default=dict, server_default=text("'{}'"))
    source_campaign_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
