"""Behavioural tests for the hold → commit/release state machine.

Regression guard: `_transition` built its timestamp-column mapping with keys and
values swapped, so `commit_hold`/`release_hold` raised KeyError on every call and
no hold could ever leave `held` — the balance stayed deducted and the row stayed
`held` forever. These tests assert the *resulting row*, not merely "no exception".
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from deerflow.persistence.credits_ledger.model import (
    STATUS_COMMITTED,
    STATUS_HELD,
    STATUS_RELEASED,
    CreditLedgerRow,
)
from deerflow.persistence.credits_ledger.sql import CreditLedgerRepository


@pytest_asyncio.fixture()
async def repo(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'ledger.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(CreditLedgerRow.__table__.create)
    yield CreditLedgerRepository(async_sessionmaker(engine, expire_on_commit=False))
    await engine.dispose()


async def _make_hold(repo: CreditLedgerRepository, hold_id: str, **kw) -> dict:
    return await repo.create_hold(
        hold_id=hold_id,
        user_id="user-1",
        amount=kw.pop("amount", 90),
        scope=kw.pop("scope", "album"),
        scope_id=kw.pop("scope_id", "album-1"),
        kind=kw.pop("kind", "generate_segment"),
        **kw,
    )


@pytest.mark.asyncio
async def test_commit_reaches_terminal_state(repo):
    await _make_hold(repo, "h-commit")

    row = await repo.commit_hold("h-commit")

    assert row["status"] == STATUS_COMMITTED
    assert row["committed_at"] is not None, "committed_at must be stamped, not left null"
    assert row["released_at"] is None, "a commit must never touch released_at"


@pytest.mark.asyncio
async def test_release_refunds_and_stamps_released_at(repo):
    await _make_hold(repo, "h-release")

    row = await repo.release_hold("h-release")

    assert row["status"] == STATUS_RELEASED
    assert row["released_at"] is not None
    assert row["committed_at"] is None, "a release must never touch committed_at"


@pytest.mark.asyncio
async def test_first_terminal_transition_wins_the_race(repo):
    """commit-then-release must not double-apply: the UPDATE only matches `held`."""
    await _make_hold(repo, "h-race")
    await repo.commit_hold("h-race")

    loser = await repo.release_hold("h-race")

    assert loser["status"] == STATUS_COMMITTED
    assert loser["released_at"] is None
    assert await repo.get_by_hold_id("h-race") is not None


@pytest.mark.asyncio
async def test_hold_is_idempotent_on_replay(repo):
    first = await _make_hold(repo, "h-replay", amount=90)

    replay = await _make_hold(repo, "h-replay", amount=500)

    assert replay["created_at"] == first["created_at"], "replay must return the original row untouched"
    assert replay["amount"] == 90, "replay must never re-charge at a new amount"
    assert replay["status"] == STATUS_HELD


@pytest.mark.asyncio
async def test_expired_hold_is_reachable_then_releasable(repo):
    """The sweeper's whole value depends on release actually working."""
    await _make_hold(repo, "h-expired", expires_at=datetime.now(UTC) - timedelta(minutes=1))
    expired = await repo.list_expired_held(before=datetime.now(UTC))
    assert [r["hold_id"] for r in expired] == ["h-expired"]

    await repo.release_hold("h-expired")

    assert await repo.list_expired_held(before=datetime.now(UTC)) == []


@pytest.mark.asyncio
async def test_transitions_do_not_disturb_untouched_holds(repo):
    await _make_hold(repo, "h-a")
    await _make_hold(repo, "h-b")

    await repo.commit_hold("h-a")

    async with repo._sf() as session:  # noqa: SLF001
        by_status = dict((await session.execute(select(CreditLedgerRow.status, func.count(CreditLedgerRow.id)).group_by(CreditLedgerRow.status))).all())
    assert by_status == {STATUS_COMMITTED: 1, STATUS_HELD: 1}
