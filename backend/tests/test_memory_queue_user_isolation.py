"""Tests for user_id propagation through memory queue (DI)."""

from unittest.mock import MagicMock, patch

from deerflow.agents.memory.backends.deermem.deermem.config import DeerMemConfig
from deerflow.agents.memory.backends.deermem.deermem.core.queue import ConversationContext, MemoryUpdateQueue


def _queue(updater: MagicMock | None = None) -> MemoryUpdateQueue:
    return MemoryUpdateQueue(DeerMemConfig(), updater or MagicMock())


def test_conversation_context_has_user_id():
    ctx = ConversationContext(thread_id="t1", messages=[], user_id="alice")
    assert ctx.user_id == "alice"


def test_conversation_context_user_id_default_none():
    ctx = ConversationContext(thread_id="t1", messages=[])
    assert ctx.user_id is None


def test_queue_add_stores_user_id():
    q = _queue()
    with patch.object(q, "_reset_timer"):
        q.add(thread_id="t1", messages=["msg"], user_id="alice")
    assert len(q._items) == 1
    assert q._items[0].user_id == "alice"
    q.clear()


def test_queue_process_passes_user_id_to_updater():
    mock_updater = MagicMock()
    mock_updater.update_memory.return_value = True
    q = _queue(mock_updater)
    with patch.object(q, "_reset_timer"):
        q.add(thread_id="t1", messages=["msg"], user_id="alice")

    q._process_queue()

    mock_updater.update_memory.assert_called_once()
    assert mock_updater.update_memory.call_args.kwargs["user_id"] == "alice"


def test_queue_keeps_updates_for_different_users_in_same_thread_and_agent():
    q = _queue()
    with patch.object(q, "_reset_timer"):
        q.add(thread_id="main", messages=["alice update"], agent_name="researcher", user_id="alice")
        q.add(thread_id="main", messages=["bob update"], agent_name="researcher", user_id="bob")

    assert q.pending_count == 2
    assert [context.user_id for context in q._items] == ["alice", "bob"]
    assert [context.messages for context in q._items] == [["alice update"], ["bob update"]]


def test_queue_still_coalesces_updates_for_same_user_thread_and_agent():
    q = _queue()
    with patch.object(q, "_reset_timer"):
        q.add(thread_id="main", messages=["first"], agent_name="researcher", user_id="alice")
        q.add(thread_id="main", messages=["second"], agent_name="researcher", user_id="alice")

    assert q.pending_count == 1
    assert q._items[0].messages == ["second"]
    assert q._items[0].user_id == "alice"
    assert q._items[0].agent_name == "researcher"


def test_add_nowait_keeps_different_users_separate():
    q = _queue()
    with patch.object(q, "_schedule_timer"):
        q.add_nowait(thread_id="main", messages=["alice update"], agent_name="researcher", user_id="alice")
        q.add_nowait(thread_id="main", messages=["bob update"], agent_name="researcher", user_id="bob")

    assert q.pending_count == 2
    assert [context.user_id for context in q._items] == ["alice", "bob"]


def test_cancel_by_agent_drops_scope_and_keeps_others():
    q = _queue()
    with patch.object(q, "_reset_timer"):
        q.add(thread_id="t1", messages=["a"], agent_name="researcher", user_id="alice")
        q.add(thread_id="t2", messages=["b"], agent_name="researcher", user_id="bob")
        q.add(thread_id="t3", messages=["c"], agent_name="other", user_id="alice")

    removed = q.cancel_by_agent("researcher", user_id="alice")
    assert removed == 1
    assert q.pending_count == 2
    assert [c.agent_name for c in q._items] == ["researcher", "other"]
    assert [c.user_id for c in q._items] == ["bob", "alice"]


def test_cancel_by_agent_all_agents_legacy_none_user_root():
    q = _queue()
    with patch.object(q, "_reset_timer"):
        q.add(thread_id="t1", messages=["a"], agent_name="researcher", user_id=None)
        q.add(thread_id="t2", messages=["b"], agent_name="other", user_id=None)
        q.add(thread_id="t3", messages=["c"], agent_name="other", user_id="alice")

    removed = q.cancel_by_agent(user_id=None, all_agents=True)
    # Only the legacy user_id None root bucket is cleared, not "every user".
    assert removed == 2
    assert q.pending_count == 1
    assert q._items[0].user_id == "alice"


def test_cancel_by_agent_empty_queue_returns_zero():
    q = _queue()
    assert q.cancel_by_agent("researcher", user_id="alice") == 0
    assert q.cancel_by_agent(user_id=None, all_agents=True) == 0


def test_cancel_by_agent_clears_and_cancels_timer_when_it_empties_queue():
    q = _queue()
    with patch.object(q, "_reset_timer"):
        q.add(thread_id="t1", messages=["a"], agent_name="researcher", user_id="alice")
    timer = q._timer
    assert q.pending_count == 1

    removed = q.cancel_by_agent("researcher", user_id="alice")
    assert removed == 1
    assert q.pending_count == 0
    if timer is not None:
        timer.cancel.assert_called_once()
