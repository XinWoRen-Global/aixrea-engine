"""Sandbox egress (outbound network) guard with allowlist/denylist and approval.

This module validates URLs extracted from sandbox command strings against
the configured egress policy, supporting three enforcement modes:

1. ``block`` — silently reject non-allowed destinations
2. ``warn`` — allow but return a warning in the output
3. ``require_approval`` — interrupt execution and ask user for approval

The matching logic follows RBAC deny-first semantics (denied matches always win),
consistent with :class:`~deerflow.authz.rbac.RbacAuthorizationProvider`.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from deerflow.guardrails.provider import GuardrailDecision, GuardrailReason, GuardrailRequest

if TYPE_CHECKING:
    from deerflow.config.sandbox_config import EgressConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExtractedUrl:
    """An extracted URL from a sandbox command."""

    url: str
    domain: str
    port: int | None
    scheme: str


@dataclass(frozen=True)
class EgressValidationResult:
    """Result of egress policy validation."""

    allowed: bool
    blocked_domains: list[str]
    blocked_ports: list[int]
    warning: str | None
    reason_code: str


def _domain_matches(pattern: str, domain: str) -> bool:
    """Check if a domain matches a pattern that can have a leading wildcard.

    Patterns:
    - ``example.com`` → exact match
    - ``*.example.com`` → any subdomain of example.com (including example.com itself)
    """
    if not pattern.startswith("*."):
        return domain.lower() == pattern.lower()

    suffix = pattern[1:].lower()  # .example.com
    domain_lower = domain.lower()
    if domain_lower == suffix[1:]:  # example.com itself
        return True
    return domain_lower.endswith(suffix)


# Regex matching well-known URL patterns in command text.
# Reuses the same pattern semantics as sandbox.tools for consistency.
_URL_IN_COMMAND_PATTERN = re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s\"'`;&|<>()]+", re.IGNORECASE)


def _extract_urls_from_command(command: str) -> list[ExtractedUrl]:
    """Extract URLs from a bash command string using regex.

    We look for anything that matches the URL scheme pattern and extract
    the full URL plus domain and port information for validation.
    """
    matches = list(re.finditer(_URL_IN_COMMAND_PATTERN, command))
    if not matches:
        return []

    results: list[ExtractedUrl] = []

    for match in matches:
        url = match.group(0)

        # Split into scheme, domain, port
        # url format: scheme://domain:port/path or scheme://domain/path
        if "://" not in url:
            continue

        scheme, rest = url.split("://", 1)

        # Split off path after domain/port
        # First component after // is authority
        authority = rest.split("/")[0].split("?")[0].split("#")[0]

        # Extract port if present
        port: int | None = None
        domain_part = authority

        if ":" in authority:
            # Handle IPv6 (we don't validate ports for IPv6)
            if "[" in authority:
                # IPv6 URL, skip port extraction
                domain_part = authority
            else:
                domain_part, port_str = authority.rsplit(":", 1)
                try:
                    port = int(port_str)
                    if port < 1 or port > 65535:
                        port = None
                except ValueError:
                    port = None

        # Strip brackets from IPv6
        domain = domain_part.strip("[]")

        results.append(
            ExtractedUrl(
                url=url,
                domain=domain,
                port=port,
                scheme=scheme,
            )
        )

    return results


def _check_domain_policy(
    url: ExtractedUrl,
    allowed_domains: list[str],
    denied_domains: list[str],
) -> bool | None:
    """Check if domain passes policy (deny-first).

    Returns:
        True = allowed, False = denied, None = no policy match (pass if allowed empty)
    """
    # Deny-first: check denied first
    for pattern in denied_domains:
        if _domain_matches(pattern, url.domain):
            logger.debug("Egress denied: domain %r matches pattern %r", url.domain, pattern)
            return False

    # If allowed list is empty, assume the operator intended to block everything:
    # an explicit ``EgressConfig`` with no allowed domains is a restrictive policy.
    if not allowed_domains:
        return False

    # Check allowed
    for pattern in allowed_domains:
        if _domain_matches(pattern, url.domain):
            logger.debug("Egress allowed: domain %r matches pattern %r", url.domain, pattern)
            return True

    # No allowed pattern matched
    logger.debug("Egress blocked: domain %r did not match any allowed pattern", url.domain)
    return False


def _check_port_policy(
    port: int | None,
    allowed_ports: list[int],
) -> bool | None:
    """Check if port passes policy.

    Returns:
        True = allowed, False = blocked, None = no policy (allow all)
    """
    if not allowed_ports:
        return None  # no restriction
    if port is None:
        # Cannot determine port → blocked by policy
        return False
    if port in allowed_ports:
        return True
    return False


def validate_egress(
    command: str,
    egress_config: EgressConfig | None,
) -> EgressValidationResult:
    """Validate a sandbox command against the configured egress policy.

    Args:
        command: The bash command to be executed in the sandbox
        egress_config: The configured egress policy (None = no control, allow all)

    Returns:
        EgressValidationResult with the decision and blocking details
    """
    # No egress control configured → allow everything
    if egress_config is None:
        return EgressValidationResult(
            allowed=True,
            blocked_domains=[],
            blocked_ports=[],
            warning=None,
            reason_code="no_policy",
        )

    urls = _extract_urls_from_command(command)
    if not urls:
        # No URLs found → allow (this doesn't mean no network access, just no URLs in command)
        return EgressValidationResult(
            allowed=True,
            blocked_domains=[],
            blocked_ports=[],
            warning=None,
            reason_code="no_urls",
        )

    blocked_domains: list[str] = []
    blocked_ports: list[int] = []

    for url in urls:
        # Check domain policy
        domain_result = _check_domain_policy(
            url,
            egress_config.allowed_domains,
            egress_config.denied_domains,
        )
        if domain_result is False:
            blocked_domains.append(url.domain)
            continue

        # Check port policy (only if domain passed)
        if url.port is not None:
            port_result = _check_port_policy(url.port, egress_config.allowed_ports)
            if port_result is False:
                blocked_ports.append(url.port)
                continue

    if not blocked_domains and not blocked_ports:
        # All URLs passed
        return EgressValidationResult(
            allowed=True,
            blocked_domains=[],
            blocked_ports=[],
            warning=None,
            reason_code="all_allowed",
        )

    # Some URLs blocked
    reason_parts: list[str] = []
    if blocked_domains:
        reason_parts.append(f"domains: {', '.join(blocked_domains)}")
    if blocked_ports:
        reason_parts.append(f"ports: {', '.join(map(str, blocked_ports))}")

    warning = f"[EGRESS POLICY WARNING] Outbound network request to blocked destinations: {', '.join(reason_parts)}"

    return EgressValidationResult(
        allowed=False,
        blocked_domains=blocked_domains,
        blocked_ports=blocked_ports,
        warning=warning,
        reason_code="policy_violation",
    )


def build_blocked_error_message(result: EgressValidationResult) -> str:
    """Build an error message for blocked egress."""
    parts: list[str] = []
    if result.blocked_domains:
        domains = ", ".join(result.blocked_domains)
        parts.append(f"disallowed domains: {domains}")
    if result.blocked_ports:
        ports = ", ".join(map(str, result.blocked_ports))
        parts.append(f"disallowed ports: {ports}")

    joined = "; ".join(parts)
    return f"Error: Sandbox egress blocked by policy: {joined}. Check your sandbox.egress configuration."


def build_warning_message(result: EgressValidationResult) -> str:
    """Build a warning message for warn-mode egress."""
    parts: list[str] = []
    if result.blocked_domains:
        domains = ", ".join(result.blocked_domains)
        parts.append(f"disallowed domains: {domains}")
    if result.blocked_ports:
        ports = ", ".join(map(str, result.blocked_ports))
        parts.append(f"disallowed ports: {ports}")

    joined = "; ".join(parts)
    return f"\n\n[WARNING] Sandbox egress policy violation: {joined}. Execution continues per 'warn' mode, but this access may be blocked in production."


# ──────────────────────────────────────────────────────────────────────
# Egress GuardrailProvider — plug into GuardrailMiddleware for full
# require_approval support at the LangGraph middleware layer.
# ──────────────────────────────────────────────────────────────────────

EGRESS_BASH_TOOL_NAMES = frozenset({"bash", "bash_tool"})


class EgressGuardrailProvider:
    """GuardrailProvider that enforces sandbox egress policy on ``bash_tool`` calls.

    When ``mode == "require_approval"`` and the command violates the egress
    policy, the provider returns a denied decision with reason code
    ``"egress.requires_approval"``. The ``GuardrailMiddleware`` converts this
    to an error ``ToolMessage``, which the agent can relay to the user for
    approval (e.g. by adding the domain to ``sandbox.egress.allowed_domains``).

    For ``block`` mode the provider returns a standard denial
    (``"egress.blocked"``), and for ``warn`` mode it returns allowed (the
    tool-level check in ``bash_tool`` already appends the warning).
    """

    name = "egress"

    def __init__(self, bash_tool_names: frozenset[str] = EGRESS_BASH_TOOL_NAMES) -> None:
        self._bash_tool_names = bash_tool_names

    def _check_egress(self, tool_name: str, tool_input: dict) -> GuardrailDecision | None:
        """Check egress policy for the given tool call.

        Returns:
            A denied ``GuardrailDecision`` if the call should be blocked, or
            ``None`` to allow the call to proceed.
        """
        if tool_name not in self._bash_tool_names:
            return None

        command = tool_input.get("command", "")
        if not command:
            return None

        try:
            from deerflow.config import get_app_config

            app_config = get_app_config()
            egress_cfg = getattr(app_config.sandbox, "egress", None) if app_config.sandbox else None
        except Exception:
            logger.warning("Could not read egress config; skipping egress guardrail check", exc_info=True)
            return None

        if egress_cfg is None:
            return None  # No egress policy configured

        result = validate_egress(command, egress_cfg)
        if result.allowed:
            return None

        if egress_cfg.mode == "warn":
            # warn mode: the tool-level check in bash_tool handles the warning
            return None

        if egress_cfg.mode == "require_approval":
            parts: list[str] = []
            if result.blocked_domains:
                parts.append(f"domains: {', '.join(result.blocked_domains)}")
            if result.blocked_ports:
                parts.append(f"ports: {', '.join(map(str, result.blocked_ports))}")
            blocked_desc = "; ".join(parts)

            return GuardrailDecision(
                allow=False,
                reasons=[
                    GuardrailReason(
                        code="egress.requires_approval",
                        message=(f"Sandbox egress requires approval: {blocked_desc}. Add the target domain to sandbox.egress.allowed_domains in your configuration to approve."),
                    )
                ],
                policy_id="egress:require_approval",
            )

        # block mode (default)
        return self._block_decision(result)

    @staticmethod
    def _block_decision(result: EgressValidationResult) -> GuardrailDecision:
        parts: list[str] = []
        if result.blocked_domains:
            parts.append(f"domains: {', '.join(result.blocked_domains)}")
        if result.blocked_ports:
            parts.append(f"ports: {', '.join(map(str, result.blocked_ports))}")
        blocked_desc = "; ".join(parts)

        return GuardrailDecision(
            allow=False,
            reasons=[
                GuardrailReason(
                    code="egress.blocked",
                    message=f"Sandbox egress blocked by policy: {blocked_desc}.",
                )
            ],
            policy_id="egress:block",
        )

    def evaluate(self, request: GuardrailRequest) -> GuardrailDecision:
        """Synchronous evaluation."""
        decision = self._check_egress(request.tool_name, request.tool_input)
        return decision if decision is not None else GuardrailDecision(allow=True)

    async def aevaluate(self, request: GuardrailRequest) -> GuardrailDecision:
        """Async evaluation (delegates to sync)."""
        return self.evaluate(request)
