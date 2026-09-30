"""Quick 单步视频轮询的任务归属校验（R2 审计 P1 回归锚点）。

漏洞：/api/ai/video/quick/poll 只校验 Gateway API Key，不校验 task_id 归属——
任一登录用户可经前端薄代理枚举他人 task_id，直接取回成片 video_url。

修复：提交成功即登记 task_id→user_id（Redis，TTL 24h 覆盖返场轮询），
轮询时由前端注入会话 user_id，归属不匹配 403；记录缺失时放行（在途任务零回归）。
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.gateway.routers import ai_proxy

pytestmark = pytest.mark.asyncio


class _FakeRedis:
    """最小 Redis 替身：只需 set/get/sadd/expire 四个动作。"""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def set(self, key, value, ex=None):  # noqa: ANN001, ANN201
        self.store[key] = value

    def get(self, key):  # noqa: ANN001, ANN201
        return self.store.get(key)

    def sadd(self, key, *members):  # noqa: ANN001, ANN201
        self.store.setdefault(key, ",".join(str(m) for m in members))

    def expire(self, key, ttl):  # noqa: ANN001, ANN201
        return None


@pytest.fixture
def fake_redis(monkeypatch):
    r = _FakeRedis()
    monkeypatch.setattr(ai_proxy, "_job_get_redis", lambda: r)
    return r


async def test_register_task_records_owner(fake_redis):
    ai_proxy._quick_register_task("user-a", "task-1")
    assert fake_redis.get(ai_proxy.QUICK_OWNER_KEY.format(task_id="task-1")) == "user-a"


async def test_assert_owner_allows_owner(fake_redis):
    ai_proxy._quick_register_task("user-a", "task-1")
    ai_proxy._quick_assert_owner("task-1", "user-a")


async def test_assert_owner_rejects_cross_user(fake_redis):
    ai_proxy._quick_register_task("user-a", "task-1")
    with pytest.raises(HTTPException) as exc_info:
        ai_proxy._quick_assert_owner("task-1", "user-b")
    assert exc_info.value.status_code == 403
    assert "TASK_FORBIDDEN" in str(exc_info.value.detail)


async def test_assert_owner_rejects_anonymous_caller(fake_redis):
    ai_proxy._quick_register_task("user-a", "task-1")
    with pytest.raises(HTTPException) as exc_info:
        ai_proxy._quick_assert_owner("task-1", "")
    assert exc_info.value.status_code == 403


async def test_assert_owner_fails_open_without_record(fake_redis):
    # 改动上线前提交的在途任务、或 Redis 抖动：无归属记录不得打断正常轮询
    ai_proxy._quick_assert_owner("legacy-task", "")


async def test_poll_rejects_cross_user(fake_redis):
    ai_proxy._quick_register_task("user-a", "task-1")
    with pytest.raises(HTTPException) as exc_info:
        await ai_proxy.quick_video_poll(task_id="task-1", provider="agnes", user_id="user-b")
    assert exc_info.value.status_code == 403


async def test_poll_owner_passes_guard(fake_redis):
    # 归属通过后继续走厂商分支：未知 provider 以 400 收尾（证明未停留在越权判定）
    ai_proxy._quick_register_task("user-a", "task-1")
    with pytest.raises(HTTPException) as exc_info:
        await ai_proxy.quick_video_poll(task_id="task-1", provider="unknown-vendor", user_id="user-a")
    assert exc_info.value.status_code == 400
