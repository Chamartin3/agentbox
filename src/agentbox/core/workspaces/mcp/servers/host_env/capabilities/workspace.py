"""agentbox.workspace_info capability tool (always granted)."""

from __future__ import annotations

from collections.abc import Callable

from agentbox.core.workspaces.mcp.servers.host_env.context import HostEnvContext
from agentbox.core.tools.grants import GrantViolation, check_capability
from agentbox.core.workspaces._types import WorkspaceInfoResult
from fastmcp import FastMCP


def register(mcp: FastMCP, ctx_factory: Callable[[], HostEnvContext]) -> None:
    @mcp.tool(
        name="agentbox.workspace_info",
        description="Read-only metadata about the current workspace. Always granted.",
    )
    def workspace_info() -> WorkspaceInfoResult:
        ctx = ctx_factory()
        try:
            check_capability(ctx.grants, "agentbox.workspace_info", {})
        except GrantViolation as exc:
            ctx.audit("agentbox.workspace_info", {}, outcome="denied", error=str(exc))
            raise
        info: WorkspaceInfoResult = {
            "workspace_id": ctx.workspace_id,
            "run_id": ctx.run_id,
            "workdir": str(ctx.workdir),
        }
        ctx.audit("agentbox.workspace_info", {}, outcome="ok")
        return info
