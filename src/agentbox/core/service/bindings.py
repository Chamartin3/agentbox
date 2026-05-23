"""Service layer for prompt + workspace resource bindings.

Wraps the agent prompt-binding CRUD, workspace file/skill bindings,
subagent assignments, and the binding-aware preview helpers that
used to live in ``api/resources/bindings.py``. Routes become a thin
transport adapter: parse → call → map domain errors to HTTP.

Workspace mutations sync the workspace on disk via an injected
``sync_cb(store, settings, name)`` callback so this module has no
transport-level dependency.

Domain errors raised here:

* :class:`BindingError` — store-level validation rejection (bad
  resource id, conflicting bindings, etc.).
* :class:`AgentVersionMissing` — no agent version found when
  previewing a prompt without a candidate template.
* :class:`PreviewError` — re-exported from
  :mod:`core.prompt.preview` so routes don't need to import it.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any, Literal

from agentbox.core.prompt.preview import (
    PreviewError,
    render_agent_prompt_preview,
)
from agentbox.core.prompt.rendering import render_for_type

if TYPE_CHECKING:
    from agentbox.core.data import SessionStore

__all__ = [
    "BindingError",
    "AgentVersionMissing",
    "PreviewError",
    # Prompt bindings
    "list_prompt_resources",
    "replace_prompt_resources",
    "preview_prompt",
    # Workspace file bindings
    "list_workspace_resources",
    "replace_workspace_resources",
    "dry_run_workspace_resources",
    # Preview helpers
    "preview_modes",
    # Subagents
    "list_workspace_subagents",
    "replace_workspace_subagents",
    # Skill bindings
    "list_workspace_skill_bindings",
    "replace_workspace_skill_bindings",
]


class BindingError(ValueError):
    """Generic binding validation rejection (raised from store ops)."""


class AgentVersionMissing(LookupError):
    def __init__(self, agent_id: str) -> None:
        super().__init__(f"no agent version found for {agent_id!r}")
        self.agent_id = agent_id


PromptMode = Literal["inline", "skill_primer", "name_only", "manifest"]
PromptSlot = Literal["system", "user_template", "input_schema", "output_schema"]


# ---------------------------------------------------------------------------
# Prompt bindings
# ---------------------------------------------------------------------------


def list_prompt_resources(agent_id: str, *, store: SessionStore) -> dict:
    bindings = store.list_prompt_bindings(agent_id)
    enriched = []
    for b in bindings:
        resource = store.get_repo_resource(b["resource_id"])
        active = store.get_active_repo_version(b["resource_id"]) if resource else None
        enriched.append(
            {
                **b,
                "attach_as_reference": bool(b.get("attach_as_reference")),
                "resource_slug": resource["slug"] if resource else None,
                "resource_type": resource["type"] if resource else None,
                "resource_display_name": resource["display_name"] if resource else None,
                "active_version_id": active["id"] if active else None,
            }
        )
    return {"items": enriched}


def replace_prompt_resources(
    agent_id: str,
    bindings: list[dict],
    *,
    store: SessionStore,
    reason: str,
    actor: str | None = None,
) -> dict:
    try:
        return {
            "items": store.replace_prompt_bindings(
                agent_id, bindings, reason=reason, actor=actor
            )
        }
    except ValueError as exc:
        raise BindingError(str(exc)) from exc


def preview_prompt(
    agent_id: str,
    *,
    store: SessionStore,
    template: str | None = None,
    bindings_override: list[dict] | None = None,
) -> dict:
    if template is None:
        active = store.get_active_version(agent_id) or store.latest_version(agent_id)
        if active is None:
            raise AgentVersionMissing(agent_id)
        template = active.get("prompt_content") or ""
    return render_agent_prompt_preview(
        store,
        agent_id=agent_id,
        template=template,
        bindings_override=bindings_override,
    )


# ---------------------------------------------------------------------------
# Workspace file bindings
# ---------------------------------------------------------------------------


def list_workspace_resources(workspace_id: str, *, store: SessionStore) -> dict:
    bindings = store.list_workspace_file_bindings(workspace_id)
    enriched = []
    for b in bindings:
        resource = store.get_repo_resource(b["resource_id"])
        active = store.get_active_repo_version(b["resource_id"]) if resource else None
        enriched.append(
            {
                **b,
                "resource_slug": resource["slug"] if resource else None,
                "resource_type": resource["type"] if resource else None,
                "active_version_id": active["id"] if active else None,
            }
        )
    return {"items": enriched}


def replace_workspace_resources(
    workspace_id: str,
    bindings: list[dict],
    *,
    store: SessionStore,
    reason: str,
    actor: str | None = None,
    settings: Any = None,
    sync_cb: Any = None,
) -> dict:
    try:
        items = store.replace_workspace_file_bindings(
            workspace_id, bindings, reason=reason, actor=actor
        )
    except ValueError as exc:
        raise BindingError(str(exc)) from exc
    if sync_cb is not None and settings is not None:
        with contextlib.suppress(Exception):
            sync_cb(store, settings, workspace_id)
    return {"items": items}


def dry_run_workspace_resources(workspace_id: str, *, store: SessionStore) -> dict:
    bindings = store.list_workspace_file_bindings(workspace_id)
    entries: list[dict] = []
    seen_paths: dict[str, str] = {}
    conflicts: list[dict] = []
    for b in bindings:
        resource = store.get_repo_resource(b["resource_id"])
        if not resource:
            conflicts.append(
                {
                    "binding_id": b["id"],
                    "issue": f"resource {b['resource_id']!r} not found",
                }
            )
            continue
        version_id = b.get("pinned_version_id")
        if not version_id:
            active = store.get_active_repo_version(b["resource_id"])
            if not active:
                conflicts.append(
                    {
                        "binding_id": b["id"],
                        "issue": f"resource {resource['slug']} has no active version",
                    }
                )
                continue
            version_id = active["id"]
        blobs = list(store.iter_repo_blobs(version_id))
        target_path = b.get("target_path") or resource["display_name"]
        entries.append(
            {
                "binding_id": b["id"],
                "resource_id": b["resource_id"],
                "resource_slug": resource["slug"],
                "resource_type": resource["type"],
                "version_id": version_id,
                "target_path": target_path,
                "file_count": len(blobs),
                "materialize_mode": b["materialize_mode"],
                "on_conflict": b["on_conflict"],
            }
        )
        if target_path in seen_paths:
            conflicts.append(
                {
                    "binding_id": b["id"],
                    "issue": (
                        f"target_path {target_path!r} also used by binding "
                        f"{seen_paths[target_path]}"
                    ),
                }
            )
        else:
            seen_paths[target_path] = b["id"]
    return {"entries": entries, "conflicts": conflicts}


# ---------------------------------------------------------------------------
# Preview helpers
# ---------------------------------------------------------------------------


def preview_modes(resource_id: str, *, store: SessionStore) -> dict:
    resource = store.get_repo_resource(resource_id)
    if not resource:
        from agentbox.core.service.resources import ResourceNotFound

        raise ResourceNotFound(resource_id)
    active = store.get_active_repo_version(resource_id)
    if not active:
        return {"modes": []}
    blobs = list(store.iter_repo_blobs(active["id"]))
    rtype = resource["type"]
    modes: list[dict] = []
    if rtype == "document":
        modes.append({"mode": "inline", **render_for_type("document", blobs)})
    if rtype == "folder":
        modes.append({"mode": "manifest", **render_for_type("folder", blobs)})
    if rtype == "skill":
        modes.append({"mode": "skill_primer", **render_for_type("skill", blobs)})
        modes.append(
            {
                "mode": "name_only",
                "text": f"- {resource['display_name']}",
                "metadata": {"role": "name_only"},
            }
        )
    return {"modes": modes}


# ---------------------------------------------------------------------------
# Subagents
# ---------------------------------------------------------------------------


def list_workspace_subagents(workspace_id: str, *, store: SessionStore) -> dict:
    items = store.list_workspace_subagents(workspace_id)
    enriched = []
    for s in items:
        agent = store.get_agent_def(s["agent_id"])
        enriched.append(
            {
                **s,
                "agent_name": getattr(agent, "name", None) if agent else None,
                "agent_description": getattr(agent, "description", None)
                if agent
                else None,
            }
        )
    return {"items": enriched}


def replace_workspace_subagents(
    workspace_id: str,
    subagents: list[dict],
    *,
    store: SessionStore,
    actor: str | None = None,
    settings: Any = None,
    sync_cb: Any = None,
) -> dict:
    try:
        items = store.replace_workspace_subagents(workspace_id, subagents, actor=actor)
    except ValueError as exc:
        raise BindingError(str(exc)) from exc
    if sync_cb is not None and settings is not None:
        with contextlib.suppress(Exception):
            sync_cb(store, settings, workspace_id)
    return {"items": items}


# ---------------------------------------------------------------------------
# Skill bindings
# ---------------------------------------------------------------------------


def list_workspace_skill_bindings(workspace_id: str, *, store: SessionStore) -> dict:
    catalog = store.list_repo_resources(type="skill", limit=500)
    current = store.list_workspace_file_bindings(workspace_id)
    bound_ids: set[str] = set()
    for b in current:
        resource = store.get_repo_resource(b["resource_id"])
        if resource and resource.get("type") == "skill":
            bound_ids.add(b["resource_id"])
    items = [{**r, "bound": r["id"] in bound_ids} for r in catalog]
    return {"items": items}


def replace_workspace_skill_bindings(
    workspace_id: str,
    skill_resource_ids: list[str],
    *,
    store: SessionStore,
    reason: str,
    actor: str | None = None,
    settings: Any = None,
    sync_cb: Any = None,
) -> dict:
    try:
        items = store.replace_workspace_skill_bindings(
            workspace_id, skill_resource_ids, reason=reason, actor=actor
        )
    except ValueError as exc:
        raise BindingError(str(exc)) from exc
    if sync_cb is not None and settings is not None:
        with contextlib.suppress(Exception):
            sync_cb(store, settings, workspace_id)
    return {"items": items}
