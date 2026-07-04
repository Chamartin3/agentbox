"""Build the agent_tools FastMCP server from the SharedToolRegistry."""

from __future__ import annotations
from typing import Any

import logging
from agentbox.core.data.constants import AGENT_TOOLS_SERVER_NAME
from agentbox.core.tools import SharedToolRegistry
from agentbox.core.data import StubResult
from agentbox.core.tools.registry import ToolSpec
from agentbox.core.workspaces.mcp.servers.agent_tools.context import AgentToolsContext
from fastmcp import FastMCP

logger = logging.getLogger(__name__)

_NOT_GRANTED = "not_granted"


def build_server(ctx: AgentToolsContext | None = None) -> FastMCP:
    """Build and return the FastMCP server.

    ctx is injected for testing; in production it is resolved from env vars.
    """
    if ctx is None:
        ctx = AgentToolsContext.from_env()

    mcp = FastMCP(
        name=AGENT_TOOLS_SERVER_NAME,
        instructions=(
            "Consumer-registered shared tools. "
            "Only tools whose names appear in the active grant set are callable."
        ),
    )

    for spec in SharedToolRegistry.all():
        if not ctx.is_granted(spec.name):
            _register_ungranted_stub(mcp, spec)
        else:
            _register_granted_tool(mcp, spec, ctx)

    return mcp


def _register_granted_tool(mcp: FastMCP, spec: ToolSpec, ctx: AgentToolsContext) -> None:
    """Register a tool whose name is in the active grant set."""
    input_model = spec.input_model

    def _tool(input: dict[str, Any]) -> dict[str, Any]:
        input_obj = input_model(**input)
        params = input_obj.model_dump()
        try:
            result = spec.fn(input_obj)
            ctx.audit(spec.name, params, "ok")
            return result.model_dump() if hasattr(result, "model_dump") else result
        except Exception as exc:
            ctx.audit(spec.name, params, "error", error=str(exc))
            raise

    _tool.__name__ = spec.name.replace(".", "_")
    mcp.tool(name=spec.name, description=spec.description)(_tool)


def _register_ungranted_stub(mcp: FastMCP, spec: ToolSpec) -> None:
    """Register a stub that returns a not-granted error for an ungranted tool."""

    def _stub() -> StubResult:
        return {"error": _NOT_GRANTED, "tool": spec.name}

    _stub.__name__ = spec.name.replace(".", "_") + "_stub"
    mcp.tool(name=spec.name, description=spec.description)(_stub)
