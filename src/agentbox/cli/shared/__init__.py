"""Shared CLI infrastructure — single import surface for all command modules.

Re-exports the public names from the sub-modules so callers can do
``from agentbox.cli.shared import console, get_store, group_callback, ...``
without knowing which sub-module owns each name.

Sub-modules
-----------
deps        singleton factories (get_settings, get_store, service factories)
context     CliCtx dataclass + Renderers registry + group_callback DI helper + error contract
constants   Style enum, NA, CLI_AUTHOR, EVENT_STYLES, JsonValue, …
render      Renderer — Rich output layer (console, checkmark, event_color)
renderers   Per-domain renderer components (AgentRenderer, EngineRenderer, …)
"""

from __future__ import annotations

from agentbox.cli.shared.constants import (
    CLI_AUTHOR,
    CLI_SOURCE,
    EPHEMERAL_WORKSPACE,
    EVENT_STYLES,
    JsonValue,
    NA,
    RUNNER_CLEAR,
    Style,
)
from agentbox.cli.shared.context import (
    CliCtx,
    Renderers,
    build_ctx,
    group_callback,
    handle_cli_errors,
    resolve_agent,
)
from agentbox.cli.shared.deps import (
    get_db,
    get_executor,
    get_mcp_registry,
    get_settings,
    get_store,
    get_agent_service,
    get_execution_service,
    get_engine_service,
    get_evaluation_service,
    get_system_service,
)
from agentbox.cli.shared.render import Renderer, checkmark, console, event_color
from agentbox.cli.shared.renderers import (
    AgentRenderer,
    EngineRenderer,
    OpsRenderer,
    RunRenderer,
    SystemRenderer,
    WorkspaceRenderer,
)

__all__ = [
    # deps — core factories
    "get_db",
    "get_executor",
    "get_mcp_registry",
    "get_settings",
    "get_store",
    # deps — service factories
    "get_agent_service",
    "get_execution_service",
    "get_engine_service",
    "get_evaluation_service",
    "get_system_service",
    # context — DI + error contract
    "CliCtx",
    "Renderers",
    "build_ctx",
    "group_callback",
    "handle_cli_errors",
    "resolve_agent",
    # constants
    "CLI_AUTHOR",
    "CLI_SOURCE",
    "EPHEMERAL_WORKSPACE",
    "EVENT_STYLES",
    "JsonValue",
    "NA",
    "RUNNER_CLEAR",
    "Style",
    # render — base class + module-level helpers
    "Renderer",
    "checkmark",
    "console",
    "event_color",
    # renderers — per-domain components
    "AgentRenderer",
    "EngineRenderer",
    "OpsRenderer",
    "RunRenderer",
    "SystemRenderer",
    "WorkspaceRenderer",
]
