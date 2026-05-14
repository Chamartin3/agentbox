"""MCP tools for resource bindings, env-docs, MCP policy, and host-env grants."""

from __future__ import annotations

import base64
import binascii
import io
import zipfile

from fastmcp import FastMCP

from agentbox.core.constants import ResourceType
from agentbox.core.env_doc.renderers import AgentsMdRenderer, ClaudeMdRenderer
from agentbox.core.resources.importers.base import ImporterContext
from agentbox.core.resources.importers.upload import UploadImporter
from agentbox.core.resources.importers.zip_upload import ZipUploadImporter
from agentbox.core.resources.prompt_resolver import resolve_prompt
from agentbox.core.run_prep import (
    resolve_agent_prompt_bindings,
    resolve_workspace_resources,
)
from agentbox.core.services.agents import resolve_agent
from agentbox.mcp_server.deps import get_context
from agentbox.mcp_server.schemas import clamp_limit

_ZIP_MAGIC = b"PK\x03\x04"
_MULTI_FILE_TYPES = {"folder", "skill"}


def _require_reason(reason: str) -> dict | None:
    if not reason or len(reason.strip()) < 3:
        return {"error": "reason_too_short", "detail": "reason must be at least 3 characters"}
    return None


def register(mcp: FastMCP) -> None:
    @mcp.tool
    def create_repo_resource(
        slug: str,
        type: str,
        display_name: str,
        description: str | None = None,
        tags: list[str] | None = None,
        content: str | None = None,
        content_base64: str | None = None,
        filename: str | None = None,
        mime_type: str | None = None,
        changelog: str | None = None,
        draft: bool = False,
    ) -> dict:
        """Create a new shared resource, optionally with an initial version.

        Calls the same ``SessionStore`` methods used by ``POST /api/repo-resources``
        and ``POST /api/repo-resources/{id}/versions/upload``.

        ``type`` is one of: document, folder, skill, schema, script.
        Provide ``content`` (text) or ``content_base64`` (binary) to also
        upload an initial version; ``changelog`` (≥ 3 chars) is required
        in that case.

        For folder/skill resources, ``content_base64`` must be a ZIP archive
        (auto-detected by magic bytes); it is dispatched to ``ZipUploadImporter``
        with ``as_skill=(type=="skill")``. To upload a multi-file skill without
        building a zip yourself, use ``create_repo_resource_from_files`` instead.
        """
        try:
            rtype = ResourceType(type)
        except ValueError:
            return {"error": "invalid_type", "detail": f"type must be one of {[t.value for t in ResourceType]}"}

        ctx = get_context()
        try:
            resource = ctx.store.create_repo_resource(
                slug=slug,
                type=rtype.value,
                display_name=display_name,
                description=description,
                tags=tags or [],
            )
        except ValueError as exc:
            return {"error": "invalid_request", "detail": str(exc)}

        result: dict = {"resource": resource}
        if content is None and content_base64 is None:
            return result

        err = _require_reason(changelog or "")
        if err:
            return {**err, "resource": resource, "hint": "provide `changelog` (≥ 3 chars) when uploading content"}

        if content_base64 is not None:
            try:
                raw = base64.b64decode(content_base64, validate=True)
            except (binascii.Error, ValueError) as exc:
                return {"error": "invalid_base64", "detail": str(exc), "resource": resource}
        else:
            raw = (content or "").encode("utf-8")

        is_zip = raw[:4] == _ZIP_MAGIC
        if rtype.value in _MULTI_FILE_TYPES:
            if not is_zip:
                return {
                    "error": "invalid_payload",
                    "detail": (
                        f"resource type {rtype.value!r} requires a ZIP archive in "
                        "`content_base64` (or use create_repo_resource_from_files)"
                    ),
                    "resource": resource,
                }
            importer = ZipUploadImporter(
                filename=filename or f"{slug.replace('/', '_')}.zip",
                content=raw,
                as_skill=(rtype.value == "skill"),
            )
        else:
            if is_zip:
                return {
                    "error": "invalid_payload",
                    "detail": (
                        f"ZIP archive given for resource type {rtype.value!r}; "
                        "ZIP uploads are only valid for type=folder or type=skill"
                    ),
                    "resource": resource,
                }
            fname = filename or f"{slug.replace('/', '_')}.md"
            importer = UploadImporter(filename=fname, content=raw, mime_type=mime_type)
        try:
            imported = importer.run(ImporterContext(actor=None, changelog=changelog))
            version = ctx.store.import_repo_version(
                resource["id"],
                imported.blobs,
                import_source=imported.import_source,
                changelog=changelog or "",
                source_metadata=imported.source_metadata,
                metadata=imported.metadata,
                draft=draft,
            )
        except ValueError as exc:
            return {"error": "import_failed", "detail": str(exc), "resource": resource}
        result["version"] = version
        return result

    @mcp.tool
    def create_repo_resource_from_files(
        slug: str,
        type: str,
        display_name: str,
        files: list[dict],
        changelog: str,
        description: str | None = None,
        tags: list[str] | None = None,
        draft: bool = False,
    ) -> dict:
        """Create a folder/skill resource from an in-line list of files.

        For MCP-only callers that cannot build a ZIP themselves. Each file
        is ``{"path": <relative path>, "content": <text>}`` or
        ``{"path": ..., "content_base64": <base64 bytes>}``. The server
        zips them and routes through ``ZipUploadImporter``.

        ``type`` must be ``"folder"`` or ``"skill"``. Skill resources
        require a ``SKILL.md`` (at the root of the supplied paths).
        ``changelog`` must be ≥ 3 chars.

        Paths must be relative POSIX paths (no leading slash, no ``..``).
        Symlinks cannot be represented; pre-resolve them at the caller.
        """
        if type not in _MULTI_FILE_TYPES:
            return {
                "error": "invalid_type",
                "detail": f"type must be 'folder' or 'skill' (got {type!r})",
            }
        err = _require_reason(changelog)
        if err:
            return err
        if not files:
            return {"error": "invalid_request", "detail": "files must be non-empty"}

        seen_paths: set[str] = set()
        entries: list[tuple[str, bytes]] = []
        for idx, item in enumerate(files):
            path = (item.get("path") or "").strip()
            if not path:
                return {"error": "invalid_request", "detail": f"files[{idx}] missing 'path'"}
            if path.startswith("/") or ".." in path.split("/") or "\\" in path:
                return {"error": "invalid_request", "detail": f"unsafe path: {path!r}"}
            if path in seen_paths:
                return {"error": "invalid_request", "detail": f"duplicate path: {path!r}"}
            seen_paths.add(path)

            if "content_base64" in item and item["content_base64"] is not None:
                try:
                    raw = base64.b64decode(item["content_base64"], validate=True)
                except (binascii.Error, ValueError) as exc:
                    return {"error": "invalid_base64", "detail": f"files[{idx}]: {exc}"}
            elif "content" in item and item["content"] is not None:
                raw = str(item["content"]).encode("utf-8")
            else:
                return {
                    "error": "invalid_request",
                    "detail": f"files[{idx}] requires 'content' or 'content_base64'",
                }
            entries.append((path, raw))

        if type == "skill" and not any(p.lower() == "skill.md" for p, _ in entries):
            return {
                "error": "invalid_request",
                "detail": "skill resources require a SKILL.md at the archive root",
            }

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for path, raw in entries:
                zf.writestr(path, raw)
        zip_bytes = buf.getvalue()

        ctx = get_context()
        try:
            resource = ctx.store.create_repo_resource(
                slug=slug,
                type=type,
                display_name=display_name,
                description=description,
                tags=tags or [],
            )
        except ValueError as exc:
            return {"error": "invalid_request", "detail": str(exc)}

        importer = ZipUploadImporter(
            filename=f"{slug.replace('/', '_')}.zip",
            content=zip_bytes,
            as_skill=(type == "skill"),
        )
        try:
            imported = importer.run(ImporterContext(actor=None, changelog=changelog))
            version = ctx.store.import_repo_version(
                resource["id"],
                imported.blobs,
                import_source=imported.import_source,
                changelog=changelog,
                source_metadata=imported.source_metadata,
                metadata=imported.metadata,
                draft=draft,
            )
        except ValueError as exc:
            return {"error": "import_failed", "detail": str(exc), "resource": resource}

        return {"resource": resource, "version": version, "file_count": len(entries)}

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
            agent = resolve_agent(agent_id, store=ctx.store, loader=ctx.loader)
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
        reason: str = "edit",
        audience: str = "both",
    ) -> dict:
        """Save the workspace env-doc — immediately live (no drafts).

        ``audience`` is 'both', 'claude_only', or 'agents_only'.
        ``reason`` is recorded for audit; it's optional and defaults to
        ``"edit"``. After saving, the workspace is re-synced so CLAUDE.md
        / AGENTS.md reflect the new content right away.
        """
        from agentbox.api.deps import get_settings
        from agentbox.core.workspace_sync import sync_workspace_by_name

        ctx = get_context()
        row = ctx.store.save_env_doc(
            workspace_id, content, changelog=reason or "edit", audience=audience
        )
        try:
            sync_workspace_by_name(ctx.store, get_settings(), workspace_id)
        except Exception:
            import logging

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
