"""Env-doc orchestration: save+sync, preview.

The env-doc is plain markdown text, stored as ``content_json = {"body": ...}``
and placed verbatim into each engine's instruction file (CLAUDE.md / AGENTS.md)
by the recipe generator.

Now delegates to ``WorkspaceService``.
"""

from __future__ import annotations

from typing import Any


def env_doc_body(content: Any) -> str:
    from agentbox.core.service.workspaces.service import env_doc_body as _body  # noqa: PLC0415
    return _body(content)


def render_env_doc_preview(content: Any) -> dict[str, str]:
    from agentbox.core.service.workspaces.service import render_env_doc_preview as _preview  # noqa: PLC0415
    return _preview(content)


def save_and_sync_env_doc(
    workspace_id: str,
    *,
    content: Any,
    reason: str = "edit",
    actor: str | None = None,
) -> dict[str, Any]:
    """Persist env-doc as live version, then sync CLAUDE.md/AGENTS.md on disk."""
    from agentbox.core.service.workspaces.service import WorkspaceService  # noqa: PLC0415
    return WorkspaceService().save_and_sync_env_doc(
        workspace_id,
        content=content,
        reason=reason,
        actor=actor,
    )
