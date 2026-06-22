"""Shared CLI infrastructure — single import surface for all command modules.

Re-exports the public names from the five sub-modules so callers can do
``from agentbox.cli.shared import console, get_store, group_callback, ...``
without knowing which sub-module owns each name.

Sub-modules
-----------
deps        singleton factories (get_settings, get_store, console, …)
context     CliCtx dataclass + group_callback DI helper
constants   Style enum, NA, CLI_AUTHOR, EVENT_STYLES, …
render      Renderer — Rich output layer
common      backwards-compat re-export shim (same names as deps)
"""

from __future__ import annotations

from agentbox.cli.shared.constants import (
    CLI_AUTHOR,
    CLI_SOURCE,
    EPHEMERAL_WORKSPACE,
    EVENT_STYLES,
    NA,
    RUNNER_CLEAR,
    Style,
)
from agentbox.cli.shared.context import CliCtx, build_ctx, group_callback
from agentbox.cli.shared.deps import (
    checkmark,
    console,
    event_color,
    get_db,
    get_executor,
    get_mcp_registry,
    get_settings,
    get_store,
    handle_cli_errors,
    resolve_agent,
)
from agentbox.cli.shared.render import Renderer

__all__ = [
    # deps
    "checkmark",
    "console",
    "event_color",
    "get_db",
    "get_executor",
    "get_mcp_registry",
    "get_settings",
    "get_store",
    "handle_cli_errors",
    "resolve_agent",
    # context
    "CliCtx",
    "build_ctx",
    "group_callback",
    # constants
    "CLI_AUTHOR",
    "CLI_SOURCE",
    "EPHEMERAL_WORKSPACE",
    "EVENT_STYLES",
    "NA",
    "RUNNER_CLEAR",
    "Style",
    # render
    "Renderer",
]
