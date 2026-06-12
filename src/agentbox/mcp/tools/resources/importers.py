"""MCP tool for creating multi-file repo resources from in-line file lists."""

from __future__ import annotations

import base64
import binascii
import io
import zipfile

from fastmcp import FastMCP

from agentbox.core.constants import ResourceType
from agentbox.core.service import (
    ImporterContext,
    ZipUploadImporter,
)
from agentbox.mcp.deps import get_context


def _require_reason(reason: str) -> dict | None:
    if not reason or len(reason.strip()) < 3:
        return {
            "error": "reason_too_short",
            "detail": "reason must be at least 3 characters",
        }
    return None


def register_importers(mcp: FastMCP) -> None:
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
        try:
            rtype = ResourceType(type)
        except ValueError:
            return {
                "error": "invalid_type",
                "detail": f"type must be 'folder' or 'skill' (got {type!r})",
            }
        if not rtype.is_multi_file:
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

        if rtype is ResourceType.SKILL and not any(p.lower() == "skill.md" for p, _ in entries):
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
                type=rtype.value,
                display_name=display_name,
                description=description,
                tags=tags or [],
            )
        except ValueError as exc:
            return {"error": "invalid_request", "detail": str(exc)}

        importer = ZipUploadImporter(
            filename=f"{slug.replace('/', '_')}.zip",
            content=zip_bytes,
            as_skill=(rtype is ResourceType.SKILL),
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
