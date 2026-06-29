"""MCP tools for repo resource creation and MCP policy management."""

from __future__ import annotations

import base64
import binascii

from fastmcp import FastMCP

from agentbox.core.constants import ResourceType
from agentbox.mcp.context import MCPContext


def _require_reason(reason: str) -> dict | None:
    if not reason or len(reason.strip()) < 3:
        return {
            "error": "reason_too_short",
            "detail": "reason must be at least 3 characters",
        }
    return None


_ZIP_MAGIC = b"PK\x03\x04"


def register_repo(mcp: FastMCP, ctx: MCPContext) -> None:
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

        Calls the same service methods used by ``POST /api/repo-resources``
        and ``POST /api/repo-resources/{id}/versions/upload``.

        ``type`` is one of: document, folder, skill, schema, script.
        Provide ``content`` (text) or ``content_base64`` (binary) to also
        upload an initial version; ``changelog`` (≥ 3 chars) is required
        in that case.

        For folder/skill resources, ``content_base64`` must be a ZIP archive
        (auto-detected by magic bytes); it is dispatched to ``import_zip_version``
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

        svc = ctx.resources()
        try:
            resource = svc.create_resource(
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
        try:
            if rtype.is_multi_file:
                if not is_zip:
                    return {
                        "error": "invalid_payload",
                        "detail": (
                            f"resource type {rtype.value!r} requires a ZIP archive in "
                            "`content_base64` (or use create_repo_resource_from_files)"
                        ),
                        "resource": resource,
                    }
                fname = filename or f"{slug.replace('/', '_')}.zip"
                version = svc.import_zip_version(
                    resource["id"],
                    filename=fname,
                    content=raw,
                    changelog=changelog or "",
                    draft=draft,
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
                version = svc.import_upload_version(
                    resource["id"],
                    filename=fname,
                    content=raw,
                    mime_type=mime_type,
                    changelog=changelog or "",
                    draft=draft,
                )
        except ValueError as exc:
            return {"error": "import_failed", "detail": str(exc), "resource": resource}
        result["version"] = version
        return result

    @mcp.tool
    def set_mcp_policy(
        workspace_id: str,
        policy: str,
        reason: str | None = None,
    ) -> dict:
        """Set the MCP server policy for a workspace.

        policy: 'allow_all_unless_disabled' | 'deny_all_unless_enabled'"""
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
        row = ctx.store.set_workspace_mcp_tool_override(
            workspace_id, server_name, tool_name, enabled=enabled
        )
        return row
