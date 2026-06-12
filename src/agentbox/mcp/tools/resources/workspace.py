"""MCP tools for workspace resources, env-doc, and host-env grants."""

from __future__ import annotations

import logging

from fastmcp import FastMCP

from agentbox.api.deps import get_settings
from agentbox.core.service import (
    EnvDocContent,
    build_workspace_by_name,
    resolve_workspace_resources,
)
from agentbox.core.service.env_doc import (
    build_env_doc_context,
    render_env_doc_preview,
)
from agentbox.mcp.deps import get_context
from agentbox.mcp.schemas import clamp_limit


def _require_reason(reason: str) -> dict | None:
    if not reason or len(reason.strip()) < 3:
        return {
            "error": "reason_too_short",
            "detail": "reason must be at least 3 characters",
        }
    return None


def register_workspace(mcp: FastMCP) -> None:
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
        rows = ctx.store.replace_workspace_file_bindings(
            workspace_id, bindings, reason=reason
        )
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
        content: dict,
        reason: str = "edit",
    ) -> dict:
        """Save the workspace env-doc — immediately live (no drafts).

        ``content`` is a structured ``EnvDocContent`` dict, with fields:
        ``project_name``, ``overview``, ``conventions[]``, ``commands[]``,
        ``sections[{id,title,body_markdown,visibility}]``, ``references``.
        Per-section ``visibility`` ('both' | 'claude_only' | 'agents_only')
        is the only audience control — there is no top-level audience.

        ``reason`` is recorded for audit; defaults to ``"edit"``.
        After saving, the workspace is re-synced so CLAUDE.md / AGENTS.md
        reflect the new content right away.
        """
        try:
            validated = EnvDocContent.model_validate(content).model_dump()
        except Exception as exc:
            return {"error": "invalid_content", "detail": str(exc)}

        ctx = get_context()
        row = ctx.store.save_env_doc(
            workspace_id, validated, changelog=reason or "edit"
        )
        try:
            build_workspace_by_name(ctx.store, get_settings(), workspace_id)
        except Exception:
            logging.getLogger(__name__).exception(
                "set_env_doc: sync failed for %s", workspace_id
            )
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

        content = EnvDocContent.model_validate(doc.get("content_json") or {})
        rctx = build_env_doc_context(ctx.store, workspace_id)
        rendered = render_env_doc_preview(content, rctx)
        result: dict = {"workspace_id": workspace_id}
        if audience != "agents_only":
            result["claude_md"] = rendered["claude_md"]
        if audience != "claude_only":
            result["agents_md"] = rendered["agents_md"]
        return result

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
        row = ctx.store.set_workspace_host_env(
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
        ctx = get_context()
        rows = ctx.store.list_host_env_calls_for_run(run_id)
        limit = clamp_limit(limit)
        return {"run_id": run_id, "calls": rows[:limit], "total": len(rows)}
