"""Evidence archival job.

Deletes evidence rows past their expires_at. Designed to run as a
periodic cron (e.g. nightly) on the VPS worker.

Phase 2: function only, no scheduler wiring yet.
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def archive_expired_evidence(session: AsyncSession) -> dict[str, int]:
    """Delete hoh_evidence rows where expires_at < NOW().

    Returns {"deleted": n}. Safe to call repeatedly.
    """
    result = await session.execute(text("DELETE FROM hoh_evidence WHERE expires_at IS NOT NULL AND expires_at < NOW()"))
    deleted = result.rowcount or 0
    await session.commit()
    logger.info("hoh evidence archival: deleted=%s", deleted)
    return {"deleted": deleted}
