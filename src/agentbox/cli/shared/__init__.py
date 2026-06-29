"""Shared CLI infrastructure — single import surface for all command modules.

Re-exports the public names from the sub-modules so callers can do
``from agentbox.cli.shared import CLIContext, group_callback, ...``
without knowing which sub-module owns each name.

Sub-modules
-----------
deps        singleton factories (get_executor, get_mcp_registry — internal to context)
context     CLIContext dataclass + Renderers registry + group_callback DI helper + error contract
constants   Style enum, NA, CLI_AUTHOR, EVENT_STYLES, JsonValue, …
render      Renderer — Rich output layer (console internal, commands use ctx.obj.render)
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
    CLIContext,
    Renderers,
    build_ctx,
    group_callback,
    handle_cli_errors,
    resolve_agent,
)
from agentbox.cli.shared.deps import (
    get_executor,
    get_mcp_registry,
)
from agentbox.cli.shared.render import Renderer
from agentbox.cli.shared.renderers import (
    AgentRenderer,
    EngineRenderer,
    OpsRenderer,
    RunRenderer,
    SystemRenderer,
    WorkspaceRenderer,
)

__all__ = [
    # context — DI + error contract
    "CLIContext",
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
    # render — base class
    "Renderer",
    # renderers — per-domain components
    "AgentRenderer",
    "EngineRenderer",
    "OpsRenderer",
    "RunRenderer",
    "SystemRenderer",
    "WorkspaceRenderer",
    # deps — documented exceptions (consumers not yet migrated to ctx.obj)
    "get_executor",
    "get_mcp_registry",
]
