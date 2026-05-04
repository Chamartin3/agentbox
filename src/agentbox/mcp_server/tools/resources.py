"""MCP tools for resource bindings, env-docs, MCP policy, and host-env grants."""

from __future__ import annotations

from fastmcp import FastMCP

from agentbox.core.env_doc.renderers import AgentsMdRenderer, ClaudeMdRenderer
from agentbox.core.resources.prompt_resolver import resolve_prompt
from agentbox.core.run_prep import (
    resolve_agent_prompt_bindings,
    resolve_workspace_resources,
)
from agentbox.mcp_server.deps import get_context
from agentbox.mcp_server.schemas import clamp_limit


def _require_reason(reason: str) -> dict | None:
    if not reason or len(reason.strip()) < 3:
        return {"error": "reason_too_short", "detail": "reason must be at least 3 characters"}
    return None


def register(mcp: FastMCP) -> None:
    @mcp.tool
    def set_prompt_resources(
        agent_id: str,
        bindings: list[dict],
        reason: str,
    ) -> dict:
        """Replace all prompt resource bindings for an agent.

        Each binding: {marker: str, resource_id: str, mode: 'embed'|'attach'}
        ``reason`` is stored as changelog; must be ≥ 3 chars."""
        err = _require_reason(reason)
        if err:
            return err
        ctx = get_context()
        rows = ctx.store.replace_prompt_bindings(agent_id, bindings, reason=reason)
        return {"agent_id": agent_id, "bindings": rows}

    @mcp.tool
    def preview_prompt(
        agent_id: str,
        template_override: str | None = None,
    ) -> dict:
        """Render the agent's system prompt with resource bindings substituted.

        Returns the rendered text plus any unresolved markers."""
        ctx = get_context()
        bindings = resolve_agent_prompt_bindings(ctx.store, agent_id)

        if template_override:
            template = template_override
        else:
            agent = ctx.loader.get(agent_id)
            if agent is None:
                return {"error": "agent_not_found", "agent_id": agent_id}
            template = agent.prompt or ""

        if not bindings:
            return {"rendered_prompt": template, "unresolved_markers": [], "resolved_count": 0}

        resolution = resolve_prompt(template, bindings)
        return {
            "rendered_prompt": resolution.rendered_prompt,
            "unresolved_markers": resolution.unresolved_markers,
            "resolved_count": len(resolution.resolved_markers),
        }

    @mcp.tool
    def set_workspace_resources(
        workspace_id: str,
        bindings: list[dict],
        reason: str,
    ) -> dict:
        """Replace all workspace file bindings for a workspace.

        Each binding: {dest_path: str, resource_id: str, mode: 'symlink'|'copy'}
        ``reason`` is stored as changelog; must be ≥ 3 chars."""
        err = _require_reason(reason)
        if err:
            return err
        ctx = get_context()
        rows = ctx.store.replace_workspace_file_bindings(workspace_id, bindings, reason=reason)
        return {"workspace_id": workspace_id, "bindings": rows}

    @mcp.tool
    def dry_run_workspace_resources(workspace_id: str) -> dict:
        """Return what would be materialized for the workspace without writing files.

        Lists each binding with its resolved resource version and target path."""
        ctx = get_context()
        bindings = resolve_workspace_resources(ctx.store, workspace_id)
        return {
            "workspace_id": workspace_id,
            "bindings": bindings,
            "count": len(bindings),
        }

    @mcp.tool
    def set_env_doc(
        workspace_id: str,
        content: str,
        reason: str,
        audience: str = "both",
    ) -> dict:
        """Save a new env-doc draft for a workspace.

        ``audience`` is 'both', 'claude_only', or 'agents_only'.
        ``reason`` must be ≥ 3 chars."""
        err = _require_reason(reason)
        if err:
            return err
        ctx = get_context()
        row = ctx.store.save_env_doc(workspace_id, content, changelog=reason, audience=audience)
        return row

    @mcp.tool
    def render_env_doc(
        workspace_id: str,
        audience: str | None = None,
    ) -> dict:
        """Preview the rendered env-doc for the workspace.

        Returns the CLAUDE.md and/or AGENTS.md content without writing files.
        audience: 'claude_only', 'agents_only', or None for both."""
        ctx = get_context()
        doc = ctx.store.get_active_env_doc(workspace_id)
        if doc is None:
            return {"workspace_id": workspace_id, "claude_md": None, "agents_md": None}

        content = doc.get("content", "")
        result: dict = {"workspace_id": workspace_id}

        if audience != "agents_only":
            result["claude_md"] = ClaudeMdRenderer().render(content)
        if audience != "claude_only":
            result["agents_md"] = AgentsMdRenderer().render(content)
        return result

    @mcp.tool
    def set_mcp_policy(
        workspace_id: str,
        policy: str,
        reason: str | None = None,
    ) -> dict:
        """Set the MCP server policy for a workspace.

        policy: 'allow_all_unless_disabled' | 'deny_all_unless_enabled'"""
        ctx = get_context()
        result = ctx.store.set_workspace_mcp_policy(workspace_id, policy)
        return {"workspace_id": workspace_id, "policy": str(result)}

    @mcp.tool
    def toggle_mcp_server(
        workspace_id: str,
        server_name: str,
        enabled: bool,
        reason: str,
    ) -> dict:
        """Enable or disable a specific MCP server in a workspace.

        ``reason`` must be ≥ 3 chars."""
        err = _require_reason(reason)
        if err:
            return err
        ctx = get_context()
        row = ctx.store.set_workspace_mcp_server_override(
            workspace_id, server_name, enabled=enabled, changelog=reason
        )
        return row

    @mcp.tool
    def toggle_mcp_tool(
        workspace_id: str,
        server_name: str,
        tool_name: str,
        enabled: bool,
        reason: str,
    ) -> dict:
        """Enable or disable a specific MCP tool in a workspace.

        ``reason`` must be ≥ 3 chars."""
        err = _require_reason(reason)
        if err:
            return err
        ctx = get_context()
        row = ctx.store.set_workspace_mcp_tool_override(
            workspace_id, server_name, tool_name, enabled=enabled, changelog=reason
        )
        return row

    @mcp.tool
    def set_host_env_grants(
        workspace_id: str,
        grants: dict,
        reason: str,
    ) -> dict:
        """Set host-env capability grants for a workspace.

        grants is a dict of capability → config, e.g.
        {'fs.read': {'allowed_paths': ['/tmp']}, 'shell.exec': {'command_allowlist': ['ls.*']}}.
        ``reason`` must be ≥ 3 chars."""
        err = _require_reason(reason)
        if err:
            return err
        ctx = get_context()
        row = ctx.store.set_workspace_host_env(workspace_id, overrides=grants, changelog=reason)
        return row

    @mcp.tool
    def list_host_env_calls(
        run_id: str,
        limit: int = 50,
    ) -> dict:
        """List host-env capability calls recorded for a run.

        Returns audit log entries: capability, status, params, error, ts."""
        ctx = get_context()
        rows = ctx.store.list_host_env_calls_for_run(run_id)
        limit = clamp_limit(limit)
        return {"run_id": run_id, "calls": rows[:limit], "total": len(rows)}
