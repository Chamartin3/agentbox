"""Backwards-compat shim.

The shared console + presentation helpers now live in
:mod:`agentbox.cli.shared.deps` (the single CLI dependency surface). This module
re-exports them so existing ``from agentbox.cli.shared.common import ...`` imports
keep working; new code should import from ``agentbox.cli.shared`` directly.
"""

from __future__ import annotations

from agentbox.cli.shared.deps import (
    EVENT_STYLES,
    checkmark,
    console,
    event_color,
    handle_cli_errors,
    resolve_agent,
)

__all__ = [
    "EVENT_STYLES",
    "checkmark",
    "console",
    "event_color",
    "handle_cli_errors",
    "resolve_agent",
]
