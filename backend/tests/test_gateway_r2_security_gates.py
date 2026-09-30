"""R2 审计安全修复的回归锚点。

覆盖第二轮审计（2026-08-29）确认的漏洞：
- config.py / rollout.py / alerts.py 管理端点无鉴权 → require_admin_user 门禁
- metrics.py 无鉴权 → METRICS_TOKEN fail-closed
- transcode.py source_url SSRF + 回调密钥外发 → allowlist
- burn.py 下载 SSRF / 磁盘耗尽 → https + host allowlist + 大小上限
- authz.py 缺 request 参数时静默跳过鉴权 → 装饰期 RuntimeError
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from app.gateway.authz import require_permission
from app.gateway.routers import alerts as alerts_router
from app.gateway.routers import burn as burn_router
from app.gateway.routers import config as config_router
from app.gateway.routers import metrics as metrics_router
from app.gateway.routers import rollout as rollout_router
from app.gateway.routers import transcode as transcode_router
from app.gateway.routers.config import ConfigUpdateRequest
from app.gateway.routers.rollout import CreateRolloutRequest

pytestmark = pytest.mark.asyncio


def _request_with_role(system_role: str):
    return SimpleNamespace(state=SimpleNamespace(user=SimpleNamespace(id="u1", system_role=system_role)))


# ─── config.py：PUT/POST 管理门禁 ───────────────────────────────────────


async def test_config_update_rejects_non_admin():
    with pytest.raises(HTTPException) as exc_info:
        await config_router.update_config(
            "feature.studio_enabled",
            ConfigUpdateRequest(value=False),
            request=_request_with_role("user"),
        )
    assert exc_info.value.status_code == 403


async def test_config_reload_rejects_non_admin():
    with pytest.raises(HTTPException) as exc_info:
        await config_router.reload_config(request=_request_with_role("user"))
    assert exc_info.value.status_code == 403


async def test_config_update_allows_admin(monkeypatch):
    async def _fake_save(config_key, value, description=None):
        return True

    async def _fake_cache(force_refresh: bool = False):
        return {}

    monkeypatch.setattr(config_router, "_save_config_to_db", _fake_save)
    monkeypatch.setattr(config_router, "_get_config_cache", _fake_cache)

    resp = await config_router.update_config(
        "feature.studio_enabled",
        ConfigUpdateRequest(value=False),
        request=_request_with_role("admin"),
    )
    assert resp["success"] is True
    assert resp["db_persisted"] is True


# ─── rollout.py：变更端点管理门禁 ───────────────────────────────────────


async def test_rollout_create_rejects_non_admin():
    body = CreateRolloutRequest(
        config_key="ai.gateway.timeout_seconds",
        strategy="percentage",
        target_value=60,
        default_value=30,
    )
    with pytest.raises(HTTPException) as exc_info:
        await rollout_router.create_rollout(body, request=_request_with_role("user"))
    assert exc_info.value.status_code == 403


async def test_rollout_delete_rejects_non_admin():
    with pytest.raises(HTTPException) as exc_info:
        await rollout_router.delete_rollout("rule-1", request=_request_with_role("user"))
    assert exc_info.value.status_code == 403


async def test_rollout_lifecycle_endpoints_reject_non_admin():
    for handler, rule_id in (
        (rollout_router.start_rollout, "r1"),
        (rollout_router.pause_rollout, "r1"),
        (rollout_router.complete_rollout, "r1"),
        (rollout_router.rollback_rollout, "r1"),
        (rollout_router.update_rollout, None),
    ):
        if handler is rollout_router.update_rollout:
            from app.gateway.routers.rollout import UpdateRolloutRequest

            with pytest.raises(HTTPException) as exc_info:
                await handler("r1", UpdateRolloutRequest(), request=_request_with_role("user"))
        else:
            with pytest.raises(HTTPException) as exc_info:
                await handler(rule_id, request=_request_with_role("user"))
        assert exc_info.value.status_code == 403, handler.__name__


async def test_rollout_create_allows_admin():
    body = CreateRolloutRequest(
        config_key="ai.gateway.timeout_seconds",
        strategy="percentage",
        target_value=60,
        default_value=30,
        name="smoke",
    )
    resp = await rollout_router.create_rollout(body, request=_request_with_role("admin"))
    assert resp["success"] is True
    # 清理内存规则，避免污染其他测试
    rollout_router.get_rollout_manager().remove_rule(resp["rule_id"])


# ─── alerts.py：ack/resolve/check 管理门禁 ──────────────────────────────


async def test_alerts_ack_rejects_non_admin():
    from app.gateway.routers.alerts import AckRequest

    with pytest.raises(HTTPException) as exc_info:
        await alerts_router.acknowledge_alert("a1", AckRequest(), request=_request_with_role("user"))
    assert exc_info.value.status_code == 403


async def test_alerts_resolve_rejects_non_admin():
    from app.gateway.routers.alerts import ResolveRequest

    with pytest.raises(HTTPException) as exc_info:
        await alerts_router.resolve_alert("a1", ResolveRequest(), request=_request_with_role("user"))
    assert exc_info.value.status_code == 403


async def test_alerts_check_rejects_non_admin():
    with pytest.raises(HTTPException) as exc_info:
        await alerts_router.check_alerts(request=_request_with_role("user"))
    assert exc_info.value.status_code == 403


async def test_alerts_ack_allows_admin(monkeypatch):
    from app.gateway.routers.alerts import AckRequest

    fake_manager = SimpleNamespace(acknowledge_alert=lambda alert_id, by: True)
    monkeypatch.setattr(alerts_router, "get_alert_manager", lambda: fake_manager)

    resp = await alerts_router.acknowledge_alert("a1", AckRequest(acknowledged_by="ops"), request=_request_with_role("admin"))
    assert resp["success"] is True
    assert resp["acknowledged_by"] == "ops"


# ─── metrics.py：METRICS_TOKEN fail-closed ──────────────────────────────


async def test_metrics_disabled_without_token(monkeypatch):
    monkeypatch.delenv("METRICS_TOKEN", raising=False)
    resp = await metrics_router.prometheus_metrics(request=_request_with_role("admin"))
    assert resp.status_code == 403


async def test_metrics_rejects_missing_token(monkeypatch):
    monkeypatch.setenv("METRICS_TOKEN", "s3cret")
    req = SimpleNamespace(headers={}, query_params={})
    resp = await metrics_router.prometheus_metrics(request=req)
    assert resp.status_code == 401


async def test_metrics_rejects_wrong_token(monkeypatch):
    monkeypatch.setenv("METRICS_TOKEN", "s3cret")
    req = SimpleNamespace(headers={"authorization": "Bearer wrong"}, query_params={})
    resp = await metrics_router.prometheus_metrics(request=req)
    assert resp.status_code == 401


async def test_metrics_accepts_valid_bearer_token(monkeypatch):
    monkeypatch.setenv("METRICS_TOKEN", "s3cret")
    req = SimpleNamespace(headers={"authorization": "Bearer s3cret"}, query_params={})
    resp = await metrics_router.prometheus_metrics(request=req)
    assert resp.status_code == 200
    assert b"deerflow_up" in resp.body


# ─── transcode.py：source_url SSRF + 回调密钥 allowlist ─────────────────


def _bypass_request():
    return SimpleNamespace(state=SimpleNamespace(), cookies={}, _deerflow_test_bypass_auth=True)


async def test_start_transcode_rejects_http_source_url():
    req = transcode_router.TranscodeRequest(
        source_key="videos/a.mp4",
        output_key_prefix="hls/a",
        source_url="http://169.254.169.254/latest/meta-data",
    )
    with pytest.raises(HTTPException) as exc_info:
        await transcode_router.start_transcode(req, request=_bypass_request())
    assert exc_info.value.status_code == 400


async def test_start_transcode_rejects_non_allowlisted_host(monkeypatch):
    monkeypatch.setattr(transcode_router, "_SOURCE_URL_HOSTS", {"r2.example.com"})
    req = transcode_router.TranscodeRequest(
        source_key="videos/a.mp4",
        output_key_prefix="hls/a",
        source_url="https://internal-service.svc.cluster.local/admin",
    )
    with pytest.raises(HTTPException) as exc_info:
        await transcode_router.start_transcode(req, request=_bypass_request())
    assert exc_info.value.status_code == 400


async def test_start_transcode_allows_allowlisted_source_url(monkeypatch):
    monkeypatch.setattr(transcode_router, "_SOURCE_URL_HOSTS", {"r2.example.com"})

    async def _fake_transcode(task):
        return {"master_playlist_url": "https://cdn.example.com/index.m3u8", "tier_urls": []}

    monkeypatch.setattr(transcode_router, "transcode_video", _fake_transcode)

    req = transcode_router.TranscodeRequest(
        source_key="videos/a.mp4",
        output_key_prefix="hls/a",
        source_url="https://r2.example.com/videos/a.mp4",
    )
    resp = await transcode_router.start_transcode(req, request=_bypass_request())
    assert resp["success"] is True


async def test_callback_auth_disabled_by_default():
    assert transcode_router._callback_should_auth("https://evil.example.com/cb") is False


async def test_callback_auth_requires_allowlisted_https_host(monkeypatch):
    monkeypatch.setattr(transcode_router, "_CALLBACK_AUTH_HOSTS", {"api.internal.example.com"})
    assert transcode_router._callback_should_auth("https://api.internal.example.com/cb") is True
    assert transcode_router._callback_should_auth("http://api.internal.example.com/cb") is False


# ─── burn.py：下载 https + allowlist + 大小上限 ─────────────────────────


async def test_burn_download_rejects_http_url():
    with pytest.raises(ValueError):
        burn_router._validate_download_url("http://169.254.169.254/latest/meta-data")


async def test_burn_download_accepts_https_when_no_allowlist(monkeypatch):
    monkeypatch.setattr(burn_router, "_BURN_SOURCE_HOSTS", set())
    burn_router._validate_download_url("https://cdn.xinworen.com/videos/a.mp4")


async def test_burn_download_enforces_allowlist_when_set(monkeypatch):
    monkeypatch.setattr(burn_router, "_BURN_SOURCE_HOSTS", {"cdn.xinworen.com"})
    burn_router._validate_download_url("https://cdn.xinworen.com/videos/a.mp4")
    with pytest.raises(ValueError):
        burn_router._validate_download_url("https://evil.example.com/a.mp4")


async def test_burn_download_enforces_size_cap(monkeypatch, tmp_path):
    monkeypatch.setattr(burn_router, "_BURN_SOURCE_HOSTS", set())
    monkeypatch.setattr(burn_router, "_MAX_DOWNLOAD_BYTES", 16)

    class _FakeResp:
        def raise_for_status(self):
            return None

        async def aiter_bytes(self, chunk_size):
            for chunk in (b"x" * 10, b"y" * 10, b"z" * 10):
                yield chunk

    class _FakeStreamCtx:
        async def __aenter__(self):
            return _FakeResp()

        async def __aexit__(self, *args):
            return False

    class _FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def stream(self, method, url):
            return _FakeStreamCtx()

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)

    dest = tmp_path / "source.bin"
    with pytest.raises(ValueError, match="exceeds"):
        await burn_router._download("https://cdn.xinworen.com/videos/a.mp4", str(dest))


# ─── authz.py：缺 request 参数 → 装饰期报错 ─────────────────────────────


async def test_require_permission_raises_at_decoration_time_without_request_param():
    with pytest.raises(RuntimeError, match="silently bypass auth"):

        @require_permission("threads", "read")
        async def _handler_without_request():  # noqa: F811
            return {}
