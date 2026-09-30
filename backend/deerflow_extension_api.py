"""
Compatibility shim for deerflow_extension_api.

This module provides the extension plugin API keys and ExtensionPrincipal class
expected by the v2.1.0 gateway code. In the official upstream, this is a separate
package installed via pip. For our custom deployment, we provide a minimal
compatible implementation.
"""

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional


# Dependency injection keys for extension plugin authorization
EXTENSION_PLUGIN_AUTHZ_RESOLVER_KEY = "extension_plugin_authz_resolver"
EXTENSION_PLUGIN_AUTHZ_RESOLVER_ASYNC_KEY = "extension_plugin_authz_resolver_async"
EXTENSION_PRINCIPAL_RESOLVER_KEY = "extension_principal_resolver"
RUN_EVIDENCE_READER_RESOLVER_KEY = "run_evidence_reader_resolver"


@dataclass
class ExtensionPrincipal:
    """Represents the authenticated principal making an extension request."""

    user_id: str
    tenant_id: Optional[str] = None
    roles: Optional[list[str]] = None
    scopes: Optional[list[str]] = None
    metadata: Optional[dict[str, Any]] = None

    def __post_init__(self):
        if self.roles is None:
            self.roles = []
        if self.scopes is None:
            self.scopes = []
        if self.metadata is None:
            self.metadata = {}
