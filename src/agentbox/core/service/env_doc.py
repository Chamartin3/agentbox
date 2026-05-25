"""Env-doc orchestration: render context, save+sync, preview."""

from __future__ import annotations

import logging
from typing import Any

from agentbox.config import Settings
from agentbox.core.data import SessionStore
from agentbox.core.workspace.env_doc.renderers import (
    AgentsMdRenderer,
    ClaudeMdRenderer,
    RuntimeContext,
)
from agentbox.core.workspace.env_doc.renderers.base import ReferenceEntry
from agentbox.core.workspace.env_doc.schema import EnvDocContent
from agentbox.core.workspace.sync import sync_workspace_by_name

_log = logging.getLogger(__name__)


def build_env_doc_context(store: SessionStore, workspace_id: str) -> RuntimeContext:
    skills: list[ReferenceEntry] = []
    folders: list[ReferenceEntry] = []
    for b in store.list_workspace_file_bindings(workspace_id):
        resource = store.get_repo_resource(b["resource_id"])
        if not resource:
            continue
        entry = ReferenceEntry(
            label=resource["display_name"], detail=b.get("target_path") or ""
        )
        if resource["type"] == "skill":
            skills.append(entry)
        elif resource["type"] == "folder":
            folders.append(entry)
    return RuntimeContext(skills=skills, folders=folders)


def render_env_doc_preview(
    content: EnvDocContent, ctx: RuntimeContext
) -> dict[str, str]:
    return {
        "claude_md": ClaudeMdRenderer().render(content, ctx),
        "agents_md": AgentsMdRenderer().render(content, ctx),
    }


def save_and_sync_env_doc(
    store: SessionStore,
    settings: Settings,
    workspace_id: str,
    *,
    content: dict[str, Any],
    reason: str = "edit",
    actor: str | None = None,
) -> dict[str, Any]:
    """Persist env-doc as live version, then sync CLAUDE.md/AGENTS.md on disk.

    Sync failures are logged but not raised — the save succeeded and the
    on-disk render is regenerated on every run anyway.
    """
    result = store.save_env_doc(
        workspace_id,
        content,
        changelog=reason,
        publish=True,
        actor=actor,
    )
    try:
        sync_workspace_by_name(store, settings, workspace_id)
    except Exception:
        _log.exception(
            "env_doc save: sync_workspace_by_name failed for %s", workspace_id
        )
    return result
