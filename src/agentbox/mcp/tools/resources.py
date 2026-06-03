"""MCP tools for resource bindings, env-docs, MCP policy, and host-env grants."""

from __future__ import annotations

import base64
import binascii
import io
import zipfile

from fastmcp import FastMCP

from agentbox.core.constants import ResourceType
from agentbox.core.agents.composition.preview import (
    PreviewError,
    render_agent_prompt_preview,
)
from agentbox.core.resource.importers.base import ImporterContext
from agentbox.core.resource.importers.upload import UploadImporter
from agentbox.core.resource.importers.zip_upload import ZipUploadImporter
from agentbox.core.execution.prepare.envdoc import (
    resolve_workspace_resources,
)
from agentbox.core.service.agents import resolve_agent
from agentbox.core.service.env_doc import (
    build_env_doc_context,
    render_env_doc_preview,
)
from agentbox.core.workspace.env_doc.schema import EnvDocContent
from agentbox.mcp.deps import get_context
from agentbox.mcp.schemas import clamp_limit

_ZIP_MAGIC = b"PK\x03\x04"
_MULTI_FILE_TYPES = {"folder", "skill"}


def _require_reason(reason: str) -> dict | None:
    if not reason or len(reason.strip()) < 3:
        return {
            "error": "reason_too_short",
            "detail": "reason must be at least 3 characters",
        }
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
            return {
                "error": "invalid_type",
                "detail": f"type must be one of {[t.value for t in ResourceType]}",
            }

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
            return {
                **err,
                "resource": resource,
                "hint": "provide `changelog` (≥ 3 chars) when uploading content",
            }

        if content_base64 is not None:
            try:
                raw = base64.b64decode(content_base64, validate=True)
            except (binascii.Error, ValueError) as exc:
                return {
                    "error": "invalid_base64",
                    "detail": str(exc),
                    "resource": resource,
                }
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
            imported = importer.run(
                ImporterContext(actor=None, changelog=changelog or "")
            )
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

    @mcp.tool(timeout=30)
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
                return {
                    "error": "invalid_request",
                    "detail": f"files[{idx}] missing 'path'",
                }
            if path.startswith("/") or ".." in path.split("/") or "\\" in path:
                return {"error": "invalid_request", "detail": f"unsafe path: {path!r}"}
            if path in seen_paths:
                return {
                    "error": "invalid_request",
                    "detail": f"duplicate path: {path!r}",
                }
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
            imported = importer.run(
                ImporterContext(actor=None, changelog=changelog or "")
            )
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
    def get_prompt_resources(agent_id: str) -> dict:
        """List the prompt resource bindings currently attached to an agent.

        Each item includes the binding id (use it for ``unbind_prompt_resource``),
        marker, mode, slot, ``attach_as_reference`` flag, pinned version, and
        enriched resource metadata (slug, type, display_name, active_version_id).
        Mirrors ``GET /api/agents/{agent_id}/prompt-resources``."""
        ctx = get_context()
        rows = ctx.store.list_prompt_bindings(agent_id)
        enriched: list[dict] = []
        for b in rows:
            resource = ctx.store.get_repo_resource(b["resource_id"])
            active = (
                ctx.store.get_active_repo_version(b["resource_id"])
                if resource
                else None
            )
            enriched.append(
                {
                    **b,
                    "attach_as_reference": bool(b.get("attach_as_reference")),
                    "resource_slug": resource["slug"] if resource else None,
                    "resource_type": resource["type"] if resource else None,
                    "resource_display_name": resource["display_name"]
                    if resource
                    else None,
                    "active_version_id": active["id"] if active else None,
                }
            )
        return {"agent_id": agent_id, "items": enriched, "count": len(enriched)}

    @mcp.tool
    def set_prompt_resources(
        agent_id: str,
        bindings: list[dict],
        reason: str,
    ) -> dict:
        """Replace all prompt resource bindings for an agent (atomic).

        Each binding: ``{resource_id, marker?, mode?, slot?,
        attach_as_reference?, pinned_version_id?, required?, display_order?}``.
        Pass an empty list to clear all bindings. ``reason`` ≥ 3 chars.

        For incremental edits prefer ``bind_prompt_resource`` /
        ``unbind_prompt_resource`` so you don't have to re-send the full list."""
        err = _require_reason(reason)
        if err:
            return err
        ctx = get_context()
        try:
            rows = ctx.store.replace_prompt_bindings(agent_id, bindings, reason=reason)
        except ValueError as exc:
            return {"error": "invalid_binding", "detail": str(exc)}
        return {"agent_id": agent_id, "bindings": rows, "count": len(rows)}

    @mcp.tool
    def bind_prompt_resource(
        agent_id: str,
        resource_id: str,
        reason: str,
        marker: str | None = None,
        mode: str | None = None,
        slot: str | None = None,
        attach_as_reference: bool = False,
        pinned_version_id: str | None = None,
        required: bool = True,
        display_order: int | None = None,
    ) -> dict:
        """Attach a single resource to an agent's prompt (incremental).

        Reads the current bindings, appends one, and writes the set back
        atomically. ``reason`` ≥ 3 chars.

        Provide ``marker`` + ``mode`` for splice bindings, ``slot`` for
        system/user_template/input_schema/output_schema bindings, or
        neither (with ``attach_as_reference=True``) for a reference-only
        binding appended under ``## References``."""
        err = _require_reason(reason)
        if err:
            return err
        ctx = get_context()
        current = ctx.store.list_prompt_bindings(agent_id)
        existing = [
            {
                "resource_id": b["resource_id"],
                "marker": b.get("marker"),
                "mode": b.get("mode"),
                "slot": b.get("slot"),
                "attach_as_reference": bool(b.get("attach_as_reference")),
                "pinned_version_id": b.get("pinned_version_id"),
                "required": bool(b.get("required", 1)),
                "display_order": int(b.get("display_order", 0)),
            }
            for b in current
        ]
        next_order = (
            display_order
            if display_order is not None
            else (max((b["display_order"] for b in existing), default=-1) + 1)
        )
        new_binding = {
            "resource_id": resource_id,
            "marker": marker,
            "mode": mode,
            "slot": slot,
            "attach_as_reference": attach_as_reference,
            "pinned_version_id": pinned_version_id,
            "required": required,
            "display_order": next_order,
        }
        try:
            rows = ctx.store.replace_prompt_bindings(
                agent_id, [*existing, new_binding], reason=reason
            )
        except ValueError as exc:
            return {"error": "invalid_binding", "detail": str(exc)}
        added = next(
            (
                r
                for r in rows
                if r["resource_id"] == resource_id
                and r.get("marker") == new_binding["marker"]
                and r.get("slot") == new_binding["slot"]
                and int(r.get("display_order", -1)) == next_order
            ),
            None,
        )
        return {
            "agent_id": agent_id,
            "added": added,
            "bindings": rows,
            "count": len(rows),
        }

    @mcp.tool
    def unbind_prompt_resource(
        agent_id: str,
        reason: str,
        binding_id: str | None = None,
        resource_id: str | None = None,
        marker: str | None = None,
        slot: str | None = None,
    ) -> dict:
        """Detach prompt resource binding(s) from an agent (incremental).

        Identify what to remove by EITHER ``binding_id`` (most specific)
        OR a filter of ``resource_id`` / ``marker`` / ``slot`` (any
        combination — all provided fields must match). At least one
        identifier is required. ``reason`` ≥ 3 chars."""
        err = _require_reason(reason)
        if err:
            return err
        if not any([binding_id, resource_id, marker, slot]):
            return {
                "error": "invalid_request",
                "detail": "provide binding_id, or any of resource_id/marker/slot",
            }
        ctx = get_context()
        current = ctx.store.list_prompt_bindings(agent_id)

        def _matches(b: dict) -> bool:
            if binding_id is not None:
                return b["id"] == binding_id
            if resource_id is not None and b["resource_id"] != resource_id:
                return False
            if marker is not None and b.get("marker") != marker:
                return False
            return not (slot is not None and b.get("slot") != slot)

        removed = [b for b in current if _matches(b)]
        if not removed:
            return {"error": "not_found", "agent_id": agent_id, "removed": []}

        keep = [
            {
                "resource_id": b["resource_id"],
                "marker": b.get("marker"),
                "mode": b.get("mode"),
                "slot": b.get("slot"),
                "attach_as_reference": bool(b.get("attach_as_reference")),
                "pinned_version_id": b.get("pinned_version_id"),
                "required": bool(b.get("required", 1)),
                "display_order": int(b.get("display_order", 0)),
            }
            for b in current
            if not _matches(b)
        ]
        try:
            rows = ctx.store.replace_prompt_bindings(agent_id, keep, reason=reason)
        except ValueError as exc:
            return {"error": "invalid_binding", "detail": str(exc)}
        return {
            "agent_id": agent_id,
            "removed": [
                {
                    "binding_id": b["id"],
                    "resource_id": b["resource_id"],
                    "marker": b.get("marker"),
                    "slot": b.get("slot"),
                }
                for b in removed
            ],
            "bindings": rows,
            "count": len(rows),
        }

    @mcp.tool
    def preview_prompt(
        agent_id: str,
        template_override: str | None = None,
    ) -> dict:
        """Render the agent's fully composed prompt with all bindings applied.

        Returns the final ``rendered_prompt`` plus a ``char_breakdown``
        showing how many characters each piece contributes (base template,
        each appended reference, input/output schema blocks), plus a
        ``snapshot`` of every resolved binding (resource_id, version_id,
        content_hash, chars). Use ``template_override`` to preview with a
        candidate prompt body instead of the agent's current one."""
        ctx = get_context()
        if template_override is None:
            agent = resolve_agent(agent_id, store=ctx.store, loader=ctx.loader)
            if agent is None:
                return {"error": "agent_not_found", "agent_id": agent_id}
            template = agent.prompt or ""
        else:
            template = template_override
        try:
            return render_agent_prompt_preview(
                ctx.store, agent_id=agent_id, template=template
            )
        except PreviewError as exc:
            return {"error": exc.code, "detail": exc.detail}

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
        from agentbox.api.deps import get_settings
        from agentbox.core.workspace.env_doc.schema import EnvDocContent
        from agentbox.core.workspace.build import build_workspace_by_name

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
            workspace_id, server_name, tool_name, enabled=enabled
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
