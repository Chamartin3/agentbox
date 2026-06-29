"""Env-doc orchestration: save+sync, preview.

The env-doc is plain markdown text, stored as ``content_json = {"body": ...}``
and placed verbatim into each engine's instruction file (CLAUDE.md / AGENTS.md)
by the recipe generator.

Now delegates to ``WorkspaceService``.
"""

from __future__ import annotations

import logging
from typing import Any

from agentbox.core.config import Settings
from agentbox.core.db import SessionStore
from agentbox.core.workspaces.build import build_workspace_by_name

_log = logging.getLogger(__name__)


def env_doc_body(content: Any) -> str:
    from agentbox.core.service.workspaces.service import env_doc_body as _body
    return _body(content)


def render_env_doc_preview(content: Any) -> dict[str, str]:
    from agentbox.core.service.workspaces.service import render_env_doc_preview as _preview
    return _preview(content)


def save_and_sync_env_doc(
    store: SessionStore,
    settings: Settings,
    workspace_id: str,
    *,
    content: Any,
    reason: str = "edit",
    actor: str | None = None,
) -> dict[str, Any]:
    """Persist env-doc as live version, then sync CLAUDE.md/AGENTS.md on disk."""
    from agentbox.core.service.workspaces.service import WorkspaceService
    svc = WorkspaceService()
    result = svc.save_env_doc(
        workspace_id,
        {"body": env_doc_body(content)},
        changelog=reason,
        publish=True,
        actor=actor,
    )
    try:
        build_workspace_by_name(store, settings, workspace_id)
    except Exception:
        _log.exception(
            "env_doc save: build_workspace_by_name failed for %s", workspace_id
        )
    return result
