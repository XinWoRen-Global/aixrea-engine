"""Tests for sandbox egress guard (allowlist/denylist and three-mode enforcement)."""

from typing import Any

from deerflow.config.sandbox_config import EgressConfig
from deerflow.guardrails.provider import GuardrailRequest
from deerflow.sandbox.egress_guard import (
    EgressGuardrailProvider,
    _check_domain_policy,
    _check_port_policy,
    _domain_matches,
    _extract_urls_from_command,
    build_blocked_error_message,
    build_warning_message,
    validate_egress,
)

# ---------- _domain_matches ----------


def test_domain_matches_exact() -> None:
    assert _domain_matches("example.com", "example.com") is True


def test_domain_matches_wildcard_subdomain() -> None:
    assert _domain_matches("*.example.com", "sub.example.com") is True


def test_domain_matches_wildcard_root() -> None:
    """Wildcard pattern *.example.com also matches example.com itself."""
    assert _domain_matches("*.example.com", "example.com") is True


def test_domain_matches_no_match() -> None:
    assert _domain_matches("example.com", "evil.com") is False


def test_domain_matches_wildcard_no_match() -> None:
    assert _domain_matches("*.example.com", "evil.com") is False


def test_domain_matches_case_insensitive() -> None:
    assert _domain_matches("Example.COM", "example.com") is True


# ---------- _extract_urls_from_command ----------


def test_extract_urls_http() -> None:
    urls = _extract_urls_from_command("curl http://example.com/path")
    assert len(urls) == 1
    assert urls[0].domain == "example.com"
    assert urls[0].port is None
    assert urls[0].scheme == "http"


def test_extract_urls_https() -> None:
    urls = _extract_urls_from_command("wget https://example.com:8080/file")
    assert len(urls) == 1
    assert urls[0].domain == "example.com"
    assert urls[0].port == 8080
    assert urls[0].scheme == "https"


def test_extract_urls_no_urls() -> None:
    urls = _extract_urls_from_command("echo hello")
    assert len(urls) == 0


def test_extract_urls_multiple() -> None:
    urls = _extract_urls_from_command("curl https://a.com && wget https://b.com:443")
    assert len(urls) == 2
    assert urls[0].domain == "a.com"
    assert urls[1].domain == "b.com"
    assert urls[1].port == 443


def test_extract_urls_inline_data() -> None:
    """data: URIs have a scheme but no host, so should not be extracted."""
    urls = _extract_urls_from_command("echo data:text/plain,hello")
    assert len(urls) == 0


def test_extract_urls_file_url() -> None:
    urls = _extract_urls_from_command("cat file:///etc/passwd")
    assert len(urls) == 1
    assert urls[0].domain == "localhost" or urls[0].domain == ""


# ---------- validate_egress: no config ----------


def test_validate_egress_no_config() -> None:
    result = validate_egress("curl https://evil.com", None)
    assert result.allowed is True
    assert result.reason_code == "no_policy"


# ---------- validate_egress: block mode ----------


def test_block_mode_allowed_domain() -> None:
    cfg = EgressConfig(allowed_domains=["example.com"], mode="block")
    result = validate_egress("curl https://example.com/api", cfg)
    assert result.allowed is True
    assert result.reason_code == "all_allowed"


def test_block_mode_blocked_domain() -> None:
    cfg = EgressConfig(allowed_domains=["example.com"], mode="block")
    result = validate_egress("curl https://evil.com", cfg)
    assert result.allowed is False
    assert result.blocked_domains == ["evil.com"]
    assert result.reason_code == "policy_violation"


def test_block_mode_deny_first() -> None:
    """Denied domains always win over allowed domains."""
    cfg = EgressConfig(
        allowed_domains=["example.com"],
        denied_domains=["internal.example.com"],
        mode="block",
    )
    result = validate_egress("curl https://internal.example.com", cfg)
    assert result.allowed is False
    assert result.blocked_domains == ["internal.example.com"]


def test_block_mode_empty_allowed() -> None:
    """Empty allowed_domains means nothing is allowed (except deny-first)."""
    cfg = EgressConfig(allowed_domains=[], mode="block")
    result = validate_egress("curl https://example.com", cfg)
    assert result.allowed is False


def test_block_mode_port_restriction() -> None:
    cfg = EgressConfig(
        allowed_domains=["example.com"],
        allowed_ports=[443],
        mode="block",
    )
    result = validate_egress("curl https://example.com:8080", cfg)
    assert result.allowed is False
    assert result.blocked_ports == [8080]


def test_block_mode_port_allowed() -> None:
    cfg = EgressConfig(
        allowed_domains=["example.com"],
        allowed_ports=[443],
        mode="block",
    )
    result = validate_egress("curl https://example.com:443", cfg)
    assert result.allowed is True


def test_block_mode_multiple_urls_one_blocked() -> None:
    cfg = EgressConfig(allowed_domains=["example.com"], mode="block")
    result = validate_egress("curl https://example.com && wget https://evil.com", cfg)
    assert result.allowed is False
    assert result.blocked_domains == ["evil.com"]


# ---------- validate_egress: warn mode ----------


def test_warn_mode_allowed() -> None:
    cfg = EgressConfig(allowed_domains=["example.com"], mode="warn")
    result = validate_egress("curl https://example.com", cfg)
    assert result.allowed is True


def test_warn_mode_blocked() -> None:
    """Warn mode returns allowed=False so the caller knows to append a warning."""
    cfg = EgressConfig(allowed_domains=["example.com"], mode="warn")
    result = validate_egress("curl https://evil.com", cfg)
    assert result.allowed is False
    assert result.warning is not None


# ---------- validate_egress: require_approval mode ----------


def test_require_approval_mode_allowed() -> None:
    cfg = EgressConfig(allowed_domains=["example.com"], mode="require_approval")
    result = validate_egress("curl https://example.com", cfg)
    assert result.allowed is True


def test_require_approval_mode_blocked() -> None:
    """require_approval mode returns allowed=False so the caller knows to ask."""
    cfg = EgressConfig(allowed_domains=["example.com"], mode="require_approval")
    result = validate_egress("curl https://evil.com", cfg)
    assert result.allowed is False
    assert result.warning is not None


# ---------- no URLs in command ----------


def test_validate_no_urls_in_command() -> None:
    cfg = EgressConfig(allowed_domains=["example.com"], mode="block")
    result = validate_egress("echo hello", cfg)
    assert result.allowed is True
    assert result.reason_code == "no_urls"


# ---------- build_blocked_error_message ----------


def test_blocked_error_message() -> None:
    from deerflow.sandbox.egress_guard import EgressValidationResult

    result = EgressValidationResult(
        allowed=False,
        blocked_domains=["evil.com"],
        blocked_ports=[],
        warning="test",
        reason_code="policy_violation",
    )
    msg = build_blocked_error_message(result)
    assert "evil.com" in msg
    assert "egress" in msg.lower()


# ---------- build_warning_message ----------


def test_warning_message() -> None:
    from deerflow.sandbox.egress_guard import EgressValidationResult

    result = EgressValidationResult(
        allowed=False,
        blocked_domains=["evil.com"],
        blocked_ports=[8080],
        warning="test",
        reason_code="policy_violation",
    )
    msg = build_warning_message(result)
    assert "evil.com" in msg
    assert "8080" in msg
    assert "WARNING" in msg


# ---------- EgressConfig validation ----------


def test_egress_config_invalid_port() -> None:
    import pytest as _pytest

    with _pytest.raises(Exception):
        EgressConfig(allowed_ports=[99999], mode="block")


def test_egress_config_empty_domain_blocked() -> None:
    import pytest as _pytest

    with _pytest.raises(Exception):
        EgressConfig(allowed_domains=[""], mode="block")


# ---------- _check_domain_policy ----------


def test_check_domain_policy_denied_wins() -> None:
    """Deny-first: denied target returns False even if also in allowed list."""
    assert (
        _check_domain_policy(
            type("", (), {"domain": "evil.com"})(),  # noqa
            allowed_domains=["evil.com"],
            denied_domains=["evil.com"],
        )
        is False
    )


def test_check_domain_policy_allowed() -> None:
    assert (
        _check_domain_policy(
            type("", (), {"domain": "good.com"})(),  # noqa
            allowed_domains=["good.com"],
            denied_domains=[],
        )
        is True
    )


# ---------- _check_port_policy ----------


def test_check_port_policy_no_restriction() -> None:
    assert _check_port_policy(443, []) is None


def test_check_port_policy_allowed() -> None:
    assert _check_port_policy(443, [443, 80]) is True


def test_check_port_policy_blocked() -> None:
    assert _check_port_policy(8080, [443]) is False


def test_check_port_policy_no_port() -> None:
    assert _check_port_policy(None, [443]) is False


# ---------- EgressGuardrailProvider (guardrails integration) ----------

# The provider calls get_app_config() internally, so we mock it at the
# original definition site.  Each test constructs a minimal mock app config
# whose sandbox.egress is the desired EgressConfig-like object.


def _make_request(
    tool_name: str = "bash",
    command: str = "",
) -> GuardrailRequest:
    """Build a GuardrailRequest with the given tool name and command."""
    return GuardrailRequest(
        tool_name=tool_name,
        tool_input={"command": command},
    )


def _mock_egress_config(
    *,
    allowed_domains: list[str] | None = None,
    denied_domains: list[str] | None = None,
    allowed_ports: list[int] | None = None,
    mode: str = "block",
) -> Any:
    """Build a lightweight mock EgressConfig to avoid Pydantic validation."""
    import unittest.mock as _m

    cfg = _m.MagicMock(spec=object)
    cfg.allowed_domains = allowed_domains or []
    cfg.denied_domains = denied_domains or []
    cfg.allowed_ports = allowed_ports or []
    cfg.mode = mode
    return cfg


def _mock_app_config(*, egress_cfg: Any | None = None) -> Any:
    """Build a mock top-level app config with sandbox.egress = egress_cfg."""
    import unittest.mock as _m

    app = _m.MagicMock(spec=object)
    sandbox = _m.MagicMock(spec=object)
    sandbox.egress = egress_cfg
    app.sandbox = sandbox
    return app


# ── non-bash / empty command ──


def test_egress_provider_skips_non_bash_tool() -> None:
    """Non-bash tools always pass through (no egress check)."""
    provider = EgressGuardrailProvider()
    request = _make_request(tool_name="read_file", command="curl https://evil.com")
    decision = provider.evaluate(request)
    assert decision.allow is True


def test_egress_provider_skips_empty_command() -> None:
    """Empty commands always pass through."""
    provider = EgressGuardrailProvider()
    request = _make_request(tool_name="bash", command="")
    decision = provider.evaluate(request)
    assert decision.allow is True


# ── no config / config load failure ──


def test_egress_provider_no_config() -> None:
    """No egress config → allow (no policy enforced)."""
    import unittest.mock as _m

    provider = EgressGuardrailProvider()
    request = _make_request(tool_name="bash", command="curl https://evil.com")

    with _m.patch("deerflow.config.get_app_config") as mock_get:
        mock_get.return_value = _mock_app_config(egress_cfg=None)
        decision = provider.evaluate(request)

    assert decision.allow is True


def test_egress_provider_config_load_exception() -> None:
    """Exception during config load → allow with a warning log."""
    import unittest.mock as _m

    provider = EgressGuardrailProvider()
    request = _make_request(tool_name="bash", command="curl https://evil.com")

    with _m.patch("deerflow.config.get_app_config") as mock_get:
        mock_get.side_effect = RuntimeError("config unavailable")
        decision = provider.evaluate(request)

    assert decision.allow is True


# ── block mode ──


def test_egress_provider_block_mode_blocked() -> None:
    """Block mode: blocked domain → deny with policy_id egress:block."""
    import unittest.mock as _m

    provider = EgressGuardrailProvider()
    cfg = _mock_egress_config(allowed_domains=["good.com"], mode="block")
    request = _make_request(tool_name="bash", command="curl https://evil.com")

    with _m.patch("deerflow.config.get_app_config") as mock_get:
        mock_get.return_value = _mock_app_config(egress_cfg=cfg)
        decision = provider.evaluate(request)

    assert decision.allow is False
    assert decision.policy_id == "egress:block"
    assert any(r.code == "egress.blocked" for r in decision.reasons)


def test_egress_provider_block_mode_allowed() -> None:
    """Block mode: allowed domain → allow."""
    import unittest.mock as _m

    provider = EgressGuardrailProvider()
    cfg = _mock_egress_config(allowed_domains=["good.com"], mode="block")
    request = _make_request(tool_name="bash", command="curl https://good.com/api")

    with _m.patch("deerflow.config.get_app_config") as mock_get:
        mock_get.return_value = _mock_app_config(egress_cfg=cfg)
        decision = provider.evaluate(request)

    assert decision.allow is True


# ── warn mode ──


def test_egress_provider_warn_mode_blocked() -> None:
    """Warn mode: blocked domain → allow (tool-level check appends warning)."""
    import unittest.mock as _m

    provider = EgressGuardrailProvider()
    cfg = _mock_egress_config(allowed_domains=["good.com"], mode="warn")
    request = _make_request(tool_name="bash", command="curl https://evil.com")

    with _m.patch("deerflow.config.get_app_config") as mock_get:
        mock_get.return_value = _mock_app_config(egress_cfg=cfg)
        decision = provider.evaluate(request)

    assert decision.allow is True


def test_egress_provider_warn_mode_allowed() -> None:
    """Warn mode: allowed domain → allow."""
    import unittest.mock as _m

    provider = EgressGuardrailProvider()
    cfg = _mock_egress_config(allowed_domains=["good.com"], mode="warn")
    request = _make_request(tool_name="bash", command="curl https://good.com")

    with _m.patch("deerflow.config.get_app_config") as mock_get:
        mock_get.return_value = _mock_app_config(egress_cfg=cfg)
        decision = provider.evaluate(request)

    assert decision.allow is True


# ── require_approval mode ──


def test_egress_provider_require_approval_blocked() -> None:
    """require_approval mode: blocked domain → deny with policy_id egress:require_approval."""
    import unittest.mock as _m

    provider = EgressGuardrailProvider()
    cfg = _mock_egress_config(allowed_domains=["good.com"], mode="require_approval")
    request = _make_request(tool_name="bash", command="curl https://evil.com")

    with _m.patch("deerflow.config.get_app_config") as mock_get:
        mock_get.return_value = _mock_app_config(egress_cfg=cfg)
        decision = provider.evaluate(request)

    assert decision.allow is False
    assert decision.policy_id == "egress:require_approval"
    assert any(r.code == "egress.requires_approval" for r in decision.reasons)
    # Verify the message mentions the user-facing approval instruction
    assert any("requires approval" in r.message for r in decision.reasons)


def test_egress_provider_require_approval_blocked_multi_domain() -> None:
    """require_approval mode: multiple blocked domains reported in reasons."""
    import unittest.mock as _m

    provider = EgressGuardrailProvider()
    cfg = _mock_egress_config(allowed_domains=["good.com"], mode="require_approval")
    request = _make_request(
        tool_name="bash",
        command="curl https://evil.com && wget https://bad.com/data",
    )

    with _m.patch("deerflow.config.get_app_config") as mock_get:
        mock_get.return_value = _mock_app_config(egress_cfg=cfg)
        decision = provider.evaluate(request)

    assert decision.allow is False
    assert decision.policy_id == "egress:require_approval"
    # The message should contain both domains
    messages = [r.message for r in decision.reasons]
    assert any("evil.com" in m for m in messages)
    assert any("bad.com" in m for m in messages)


def test_egress_provider_require_approval_allowed() -> None:
    """require_approval mode: allowed domain → allow."""
    import unittest.mock as _m

    provider = EgressGuardrailProvider()
    cfg = _mock_egress_config(allowed_domains=["good.com"], mode="require_approval")
    request = _make_request(tool_name="bash", command="curl https://good.com")

    with _m.patch("deerflow.config.get_app_config") as mock_get:
        mock_get.return_value = _mock_app_config(egress_cfg=cfg)
        decision = provider.evaluate(request)

    assert decision.allow is True


# ── block mode with port restriction ──


def test_egress_provider_block_mode_port_restriction() -> None:
    """Block mode: port mismatch → deny with egress.blocked."""
    import unittest.mock as _m

    provider = EgressGuardrailProvider()
    cfg = _mock_egress_config(
        allowed_domains=["good.com"],
        allowed_ports=[443],
        mode="block",
    )
    request = _make_request(tool_name="bash", command="curl https://good.com:8080")

    with _m.patch("deerflow.config.get_app_config") as mock_get:
        mock_get.return_value = _mock_app_config(egress_cfg=cfg)
        decision = provider.evaluate(request)

    assert decision.allow is False
    assert decision.policy_id == "egress:block"


# ── aevaluate (async) ──


def test_egress_provider_aevaluate_delegates_to_evaluate() -> None:
    """aevaluate returns the same result as evaluate for a given request."""
    import unittest.mock as _m

    provider = EgressGuardrailProvider()
    cfg = _mock_egress_config(allowed_domains=["good.com"], mode="block")
    request = _make_request(tool_name="bash", command="curl https://evil.com")

    with _m.patch("deerflow.config.get_app_config") as mock_get:
        mock_get.return_value = _mock_app_config(egress_cfg=cfg)

        import asyncio as _asyncio

        sync_decision = provider.evaluate(request)
        async_decision = _asyncio.run(provider.aevaluate(request))

    assert sync_decision.allow == async_decision.allow
    assert sync_decision.policy_id == async_decision.policy_id


# ── custom bash_tool_names ──


def test_egress_provider_custom_tool_names() -> None:
    """Custom bash_tool_names set restricts which tools are checked."""
    import unittest.mock as _m

    provider = EgressGuardrailProvider(bash_tool_names=frozenset({"my_bash"}))
    cfg = _mock_egress_config(allowed_domains=["good.com"], mode="block")
    request_my_bash = _make_request(tool_name="my_bash", command="curl https://evil.com")
    request_bash = _make_request(tool_name="bash", command="curl https://evil.com")

    with _m.patch("deerflow.config.get_app_config") as mock_get:
        mock_get.return_value = _mock_app_config(egress_cfg=cfg)
        decision_my_bash = provider.evaluate(request_my_bash)
        decision_bash = provider.evaluate(request_bash)

    # my_bash is in the custom set → checked
    assert decision_my_bash.allow is False
    assert decision_my_bash.policy_id == "egress:block"
    # bash is NOT in the custom set → skipped
    assert decision_bash.allow is True
