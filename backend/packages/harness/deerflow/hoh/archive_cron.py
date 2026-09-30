"""HoH evidence archival cron entrypoint.

Run on the VPS nightly (or hourly) to delete expired evidence rows.

Usage:
    python -m deerflow.hoh.archive_cron
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("hoh.archive_cron")


async def main() -> None:
    db_url = os.environ.get("DATABASE_URL") or os.environ.get("CHECKPOINTER_DB_URL")
    if not db_url:
        logger.error("DATABASE_URL not set; skipping archive")
        sys.exit(1)

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    engine = create_async_engine(db_url, pool_size=1, max_overflow=0)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    from deerflow.hoh.archive import archive_expired_evidence

    async with factory() as session:
        result = await archive_expired_evidence(session)

    await engine.dispose()
    logger.info("archive done: %s", result)


if __name__ == "__main__":
    asyncio.run(main())
