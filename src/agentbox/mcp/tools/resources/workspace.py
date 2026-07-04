"""MCP tools for workspace resources, env-doc, and host-env grants."""

from __future__ import annotations

import logging

from fastmcp import FastMCP

from agentbox.core.data.payload_types import WorkspaceBindingSpec
from agentbox.core.data.rows import EnvDocRow, WorkspaceHostEnvGrantRow
from agentbox.core.service import render_env_doc_preview
from agentbox.mcp.context import MCPContext
from agentbox.mcp.schemas import clamp_limit


def _require_reason(reason: str) -> dict | None:
    if not reason or len(reason.strip()) < 3:
        return {
            "error": "reason_too_short",
            "detail": "reason must be at least 3 characters",
        }
    return None


def register_workspace(mcp: FastMCP, ctx: MCPContext) -> None:
    @mcp.tool
    def set_workspace_resources(
        workspace_id: str,
        bindings: list[dict],
        reason: str,
    ) -> dict:
        """Replace all workspace file bindings for a workspace.

        Each binding: {dest_path: str, resource_id: str, mode: 'symlink'|'copy'}
        or {target_path: str, resource_id: str, materialize_mode: str}.
        ``reason`` is stored as changelog; must be ≥ 3 chars."""
        err = _require_reason(reason)
        if err:
            return err
        # Normalize loose field names from MCP callers to canonical schema.
        normalized: list[WorkspaceBindingSpec] = [
            {
                "resource_id": b["resource_id"],
                "target_path": b.get("target_path") or b.get("dest_path"),
                "materialize_mode": b.get("materialize_mode") or b.get("mode", "copy"),
                "on_conflict": b.get("on_conflict", "error"),
                "pinned_version_id": b.get("pinned_version_id"),
                "display_order": b.get("display_order", 0),
            }
            for b in bindings
        ]
        svc = ctx.resources
        try:
            rows = svc.replace_workspace_resources(
                workspace_id, normalized, reason=reason
            )["items"]
        except ValueError as exc:
            return {"error": "invalid_binding", "detail": str(exc)}
        return {"workspace_id": workspace_id, "bindings": rows}

    @mcp.tool
    def dry_run_workspace_resources(workspace_id: str) -> dict:
        """Return what would be materialized for the workspace without writing files.

        Lists each binding with its resolved resource version and target path."""
        svc = ctx.resources
        result = svc.dry_run_workspace_resources(workspace_id)
        return {
            "workspace_id": workspace_id,
            "bindings": result["entries"],
            "conflicts": result["conflicts"],
            "count": len(result["entries"]),
        }

    @mcp.tool
    def set_env_doc(
        workspace_id: str,
        content: str,
        reason: str = "edit",
    ) -> EnvDocRow:
        """Save the workspace env-doc — immediately live (no drafts).

        ``content`` is the raw markdown body. It is placed verbatim into the
        workspace's CLAUDE.md / AGENTS.md by the recipe generator.

        ``reason`` is recorded for audit; defaults to ``"edit"``.
        After saving, the workspace is re-synced so CLAUDE.md / AGENTS.md
        reflect the new content right away.
        """
        try:
            return ctx.workspaces.save_and_sync_env_doc(
                workspace_id, content=content, reason=reason or "edit"
            )
        except Exception:
            logging.getLogger(__name__).exception(
                "set_env_doc: save_and_sync_env_doc failed for %s", workspace_id
            )
            raise

    @mcp.tool
    def render_env_doc(workspace_id: str) -> dict:
        """Preview the rendered env-doc for the workspace.

        Returns the CLAUDE.md / AGENTS.md content (identical body) without
        writing files."""
        doc = ctx.workspaces.get_active_env_doc(workspace_id)
        if doc is None:
            return {"workspace_id": workspace_id, "claude_md": None, "agents_md": None}

        rendered = render_env_doc_preview(doc.get("content_json") or {})
        return {
            "workspace_id": workspace_id,
            "claude_md": rendered["claude_md"],
            "agents_md": rendered["agents_md"],
        }

    @mcp.tool
    def set_host_env_grants(
        workspace_id: str,
        grants: dict,
        reason: str,
    ) -> WorkspaceHostEnvGrantRow | dict:
        """Set host-env capability grants for a workspace.

        grants is a dict of capability → config, e.g.
        {'fs.read': {'allowed_paths': ['/tmp']}, 'shell.exec': {'command_allowlist': ['ls.*']}}.
        ``reason`` must be ≥ 3 chars."""
        err = _require_reason(reason)
        if err:
            return err
        row = ctx.workspaces.set_workspace_host_env(
            workspace_id, profile_id=None, overrides=grants, changelog=reason
        )
        return row

    @mcp.tool
    def list_host_env_calls(
        run_id: str,
        limit: int = 50,
    ) -> dict:
        """List host-env capability calls recorded for a run.

        Returns audit log entries: capability, status, params, error, ts."""
        rows = ctx.system.list_host_env_calls_for_run(run_id)
        limit = clamp_limit(limit)
        return {"run_id": run_id, "calls": rows[:limit], "total": len(rows)}
