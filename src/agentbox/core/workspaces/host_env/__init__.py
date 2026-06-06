"""Host-environment MCP server primitives (Plan 06).

Re-exports from canonical locations. Prefer importing directly from
:mod:`agentbox.core.tools` (Capability, CAPABILITIES) and
:mod:`agentbox.core.workspaces.permissions` (GrantViolation, check_capability,
resolve_grants).
"""

from agentbox.core.tools.capabilities import CAPABILITIES, Capability
from agentbox.core.workspaces.permissions import (
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
