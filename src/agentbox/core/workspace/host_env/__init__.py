"""Host-environment MCP server primitives (Plan 06).

This package houses the capability registry, permission/grant resolver,
and a stub for the FastMCP server. The server process itself is out of
scope for the foundation drop — the data model + permission resolver
land here so the API can edit grants and runs can check them.
"""

from agentbox.core.workspace.host_env.capabilities import CAPABILITIES, Capability
from agentbox.core.workspace.host_env.permissions import (
    GrantViolation,
    check_capability,
    resolve_grants,
)

__all__ = [
    "CAPABILITIES",
    "Capability",
    "GrantViolation",
    "check_capability",
    "resolve_grants",
]
