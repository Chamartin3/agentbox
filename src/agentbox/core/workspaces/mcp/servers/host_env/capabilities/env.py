"""env.get capability tool."""

from __future__ import annotations

import os
from collections.abc import Callable

from agentbox.core.workspaces.mcp.servers.host_env.context import HostEnvContext
from agentbox.core.tools.grants import GrantViolation, check_capability
from fastmcp import FastMCP


def register(mcp: FastMCP, ctx_factory: Callable[[], HostEnvContext]) -> None:
    @mcp.tool(
        name="env.get",
        description="Read an allowlisted environment variable. Requires env.get grant.",
    )
    def env_get(name: str) -> str | None:
        ctx = ctx_factory()
        try:
            check_capability(ctx.grants, "env.get", {"name": name})
        except GrantViolation as exc:
            ctx.audit("env.get", {"name": name}, outcome="denied", error=str(exc))
            raise
        value = os.environ.get(name)
        ctx.audit("env.get", {"name": name}, outcome="ok")
        return value
