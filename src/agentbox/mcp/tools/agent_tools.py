"""Control-plane MCP tools for agent tool grant management."""

from __future__ import annotations

from fastmcp import FastMCP

from agentbox.mcp.context import MCPContext


def register(mcp: FastMCP, ctx: MCPContext) -> None:
    @mcp.tool(
        name="list_agent_tools",
        description="List all consumer-registered shared agent tools discovered at startup.",
    )
    def list_agent_tools(tags: list[str] | None = None) -> dict:
        specs = ctx.engines.list_shared_tools()
        if tags:
            specs = [s for s in specs if set(tags) & set(s.tags)]
        return {
            "items": [
                {
                    "name": s.name,
                    "description": s.description,
                    "capability": s.capability,
                    "tags": list(s.tags),
                }
                for s in specs
            ]
        }

    @mcp.tool(
        name="list_agent_tool_grants",
        description="List tool grants for an agent.",
    )
    def list_agent_tool_grants(agent_id: str, include_revoked: bool = False) -> dict:
        return {"items": ctx.agents.list_tool_grants(agent_id, include_revoked)}

    @mcp.tool(
        name="grant_agent_tool",
        description=(
            "Grant a shared tool to an agent. "
            "The reason/changelog is mandatory (min 3 chars)."
        ),
    )
    def grant_agent_tool(
        agent_id: str,
        tool_name: str,
        reason: str,
        actor: str | None = None,
    ) -> dict:
        if len(reason.strip()) < 3:
            return {"error": "reason must be at least 3 characters"}
        try:
            row = ctx.agents.grant_tool(agent_id, tool_name, reason, actor)
            return dict(row)
        except ValueError as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="revoke_agent_tool",
        description="Revoke a previously granted tool from an agent (soft-delete).",
    )
    def revoke_agent_tool(
        agent_id: str,
        tool_name: str,
        reason: str,
        actor: str | None = None,
    ) -> dict:
        if len(reason.strip()) < 3:
            return {"error": "reason must be at least 3 characters"}
        try:
            ctx.agents.revoke_tool(agent_id, tool_name, reason, actor)
            return {"revoked": True}
        except ValueError as exc:
            return {"error": str(exc)}
