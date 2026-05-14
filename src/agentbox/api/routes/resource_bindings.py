"""Agent + workspace resource binding routes (Plans 02 + 03).

Atomic PUT replaces the whole binding set for an agent/workspace, with
a mandatory reason. Includes a preview/dry-run endpoint per side.
"""

from __future__ import annotations

import contextlib
import json
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agentbox.api.deps import get_settings, get_store
from agentbox.core.composition import _append_input_schema, _append_schema
from agentbox.core.data.store import SessionStore
from agentbox.core.resources.prompt_resolver import resolve_prompt
from agentbox.core.resources.rendering import render_for_type
from agentbox.core.workspace_sync import sync_workspace_by_name

router = APIRouter(tags=["resource-bindings"])

PromptMode = Literal["inline", "skill_primer", "name_only", "manifest"]
PromptSlot = Literal["system", "user_template", "input_schema", "output_schema"]
MaterializeMode = Literal["copy", "symlink", "mount"]
OnConflict = Literal["error", "overwrite", "skip"]


class PromptBindingIn(BaseModel):
    resource_id: str
    marker: str | None = None
    mode: PromptMode | None = None
    slot: PromptSlot | None = None
    attach_as_reference: bool = False
    pinned_version_id: str | None = None
    required: bool = True
    display_order: int = 0


class ReplacePromptBindings(BaseModel):
    bindings: list[PromptBindingIn]
    reason: str = Field(default="ui edit", min_length=1)
    actor: str | None = None


class SubagentIn(BaseModel):
    agent_id: str
    alias: str
    display_order: int = 0


class ReplaceSubagents(BaseModel):
    subagents: list[SubagentIn]
    actor: str | None = None


class WorkspaceBindingIn(BaseModel):
    resource_id: str
    target_path: str | None = None
    materialize_mode: MaterializeMode = "copy"
    on_conflict: OnConflict = "error"
    pinned_version_id: str | None = None
    display_order: int = 0


class ReplaceWorkspaceBindings(BaseModel):
    bindings: list[WorkspaceBindingIn]
    reason: str = Field(default="ui edit", min_length=1)
    actor: str | None = None


# --- helpers ---


def _resolve_binding_for_prompt(store: SessionStore, b: dict) -> dict:
    resource = store.get_repo_resource(b["resource_id"])
    if not resource:
        raise HTTPException(status_code=400, detail=f"resource {b['resource_id']!r} not found")
    version_id = b.get("pinned_version_id")
    if not version_id:
        active = store.get_active_repo_version(b["resource_id"])
        if not active:
            raise HTTPException(
                status_code=400,
                detail=f"resource {b['resource_id']!r} has no active version",
            )
        version_id = active["id"]
    version = store.get_repo_version(version_id)
    blobs = list(store.iter_repo_blobs(version_id))
    return {
        "binding_id": b["id"],
        "marker": b.get("marker"),
        "slot": b.get("slot"),
        "attach_as_reference": bool(b.get("attach_as_reference")),
        "resource_id": b["resource_id"],
        "resource_slug": resource["slug"],
        "version_id": version_id,
        "content_hash": version["content_hash"],
        "type": resource["type"],
        "mode": b.get("mode"),
        "display_name": resource["display_name"],
        "required": bool(b.get("required", 1)),
        "blobs": blobs,
    }


def _render_references_block(
    resolved: list[dict],
) -> tuple[str, list[dict], list[dict]]:
    """Render the References section for prompt bindings flagged
    ``attach_as_reference``. Returns ``(text, refs_meta, per_ref_chars)``.

    ``per_ref_chars`` is a list of ``{label, chars}`` entries (one per
    rendered reference) suitable for inclusion in the char-breakdown
    visualization.
    """
    parts: list[str] = []
    refs_meta: list[dict] = []
    per_ref_chars: list[dict] = []
    for b in resolved:
        if not b.get("attach_as_reference"):
            continue
        # Slot bindings (system/user_template/input_schema/output_schema)
        # have dedicated rendering — skip them here to avoid duplication.
        if b.get("slot"):
            continue
        if b["type"] not in ("document", "folder"):
            continue
        rendered = render_for_type(b["type"], b.get("blobs") or [])
        heading = b.get("display_name") or b.get("resource_slug") or b["resource_id"]
        body = rendered.get("text") or ""
        if body:
            entry = f"## {heading}\n\n{body}"
            parts.append(entry)
            # +2 for the "\n\n" separator joining entries
            per_ref_chars.append({"label": heading, "chars": len(entry) + 2})
        refs_meta.append(
            {
                "binding_id": b["binding_id"],
                "resource_id": b["resource_id"],
                "version_id": b["version_id"],
                "display_name": b.get("display_name"),
            }
        )
    if not parts:
        return "", refs_meta, per_ref_chars
    # Account for the "## References\n\n" header chars on the first entry.
    if per_ref_chars:
        per_ref_chars[0]["chars"] += len("## References\n\n")
    return "## References\n\n" + "\n\n".join(parts), refs_meta, per_ref_chars


def _schema_for_slot(resolved: list[dict], slot: str) -> dict | None:
    for b in resolved:
        if b.get("slot") == slot and b.get("attach_as_reference"):
            rendered = render_for_type(b["type"], b.get("blobs") or [])
            return {
                "binding_id": b["binding_id"],
                "resource_id": b["resource_id"],
                "version_id": b["version_id"],
                "display_name": b.get("display_name"),
                "content_hash": b["content_hash"],
                "text": rendered.get("text") or "",
            }
    return None


# --- prompt bindings (Plan 02) ---


@router.get("/api/agents/{agent_id}/prompt-resources")
def list_prompt_resources(
    agent_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
):
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


@router.put("/api/agents/{agent_id}/prompt-resources")
def replace_prompt_resources(
    agent_id: str,
    body: ReplacePromptBindings,
    store: Annotated[SessionStore, Depends(get_store)],
):
    try:
        return {
            "items": store.replace_prompt_bindings(
                agent_id,
                [b.model_dump() for b in body.bindings],
                reason=body.reason,
                actor=body.actor,
            )
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class PreviewPromptBody(BaseModel):
    template: str
    bindings: list[PromptBindingIn] | None = None


@router.post("/api/agents/{agent_id}/prompt-resources/preview")
def preview_prompt(
    agent_id: str,
    body: PreviewPromptBody,
    store: Annotated[SessionStore, Depends(get_store)],
):
    # Use posted bindings if provided, else live bindings.
    if body.bindings is not None:
        raw = [{**b.model_dump(), "id": f"preview-{i}"} for i, b in enumerate(body.bindings)]
    else:
        raw = store.list_prompt_bindings(agent_id)
    resolved = [_resolve_binding_for_prompt(store, b) for b in raw]
    # When a system slot binding is active, its rendered text replaces
    # the posted template (which is the legacy on-disk prompt). This
    # makes the preview match what BindingsBundleSource feeds the runner.
    system_view = _schema_for_slot(resolved, "system")
    template_text = (
        system_view["text"] if system_view and system_view.get("text")
        else body.template
    )
    # Only marker-style (non-slot) bindings participate in splicing.
    splice_bindings = [b for b in resolved if b.get("marker") and b.get("mode")]
    result = resolve_prompt(template_text, splice_bindings)

    refs_text, refs_meta, per_ref_chars = _render_references_block(resolved)
    base_prompt = result.rendered_prompt
    composed = base_prompt

    input_schema = _schema_for_slot(resolved, "input_schema")
    output_schema = _schema_for_slot(resolved, "output_schema")
    raw_text_output = output_schema is None

    # Inline schemas via the same runtime helpers
    # (core/composition/prompts/{input,output}_schema.md). Falls back to
    # raw text if the schema is not valid JSON.
    def _schema_block(slot: str, schema_view: dict | None) -> str:
        if not schema_view or not schema_view.get("text"):
            return ""
        text = schema_view["text"]
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError):
            parsed = None
        if isinstance(parsed, dict):
            if slot == "input_schema":
                return _append_input_schema("", parsed)
            return _append_schema("", parsed)
        header = (
            "# Input Format" if slot == "input_schema" else "# Required Output"
        )
        return f"{header}\n\n## JSON Schema\n\n```json\n{text}\n```"

    input_schema_block = _schema_block("input_schema", input_schema)
    if input_schema_block:
        composed = composed.rstrip() + "\n\n" + input_schema_block

    if refs_text:
        composed = composed.rstrip() + "\n\n" + refs_text

    output_schema_block = _schema_block("output_schema", output_schema)
    if output_schema_block:
        composed = composed.rstrip() + "\n\n" + output_schema_block

    parts = [
        {"label": "prompt template", "chars": len(base_prompt)},
    ]
    if input_schema_block:
        parts.append({"label": "input_schema block", "chars": len(input_schema_block) + 2})
    if refs_text:
        parts.extend(per_ref_chars)
    if output_schema_block:
        parts.append({"label": "output_schema block", "chars": len(output_schema_block) + 2})

    return {
        "rendered_prompt": composed,
        "unresolved_markers": result.unresolved_markers,
        "warnings": result.warnings,
        "references": refs_meta,
        "input_schema": input_schema,
        "output_schema": output_schema,
        "raw_text_output": raw_text_output,
        "char_breakdown": parts,
        "total_chars": len(composed),
        "snapshot": [
            {
                "binding_id": rb.binding_id,
                "marker": rb.marker,
                "resource_id": rb.resource_id,
                "version_id": rb.version_id,
                "content_hash": rb.content_hash,
                "mode": rb.mode,
            }
            for rb in result.snapshot
        ],
    }


# --- workspace file bindings (Plan 03) ---


@router.get("/api/workspaces/{workspace_id}/resources")
def list_workspace_resources(
    workspace_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
):
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


@router.put("/api/workspaces/{workspace_id}/resources")
def replace_workspace_resources(
    workspace_id: str,
    body: ReplaceWorkspaceBindings,
    store: Annotated[SessionStore, Depends(get_store)],
):
    try:
        items = store.replace_workspace_file_bindings(
            workspace_id,
            [b.model_dump() for b in body.bindings],
            reason=body.reason,
            actor=body.actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Phase 1: re-materialize the workspace on disk after the DB write.
    with contextlib.suppress(Exception):
        sync_workspace_by_name(store, get_settings(), workspace_id)
    return {"items": items}


@router.post("/api/workspaces/{workspace_id}/resources/dry-run")
def dry_run_workspace_resources(
    workspace_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
):
    """Compute the file tree that current bindings would materialize.

    Does not touch the filesystem; reports the (target_path, file_count,
    mode) per binding and flags any overlapping target paths.
    """
    bindings = store.list_workspace_file_bindings(workspace_id)
    entries = []
    seen_paths: dict[str, str] = {}
    conflicts: list[dict] = []
    for b in bindings:
        resource = store.get_repo_resource(b["resource_id"])
        if not resource:
            conflicts.append(
                {"binding_id": b["id"], "issue": f"resource {b['resource_id']!r} not found"}
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
                    "issue": f"target_path {target_path!r} also used by binding {seen_paths[target_path]}",
                }
            )
        else:
            seen_paths[target_path] = b["id"]
    return {"entries": entries, "conflicts": conflicts}


# --- preview rendering (no bindings, just a single resource preview) ---


@router.get("/api/repo-resources/{resource_id}/preview-modes")
def preview_modes(resource_id: str, store: Annotated[SessionStore, Depends(get_store)]):
    """Return the prompt-embed rendering for each mode valid for this type."""
    resource = store.get_repo_resource(resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="resource not found")
    active = store.get_active_repo_version(resource_id)
    if not active:
        return {"modes": []}
    blobs = list(store.iter_repo_blobs(active["id"]))
    rtype = resource["type"]
    modes = []
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


# --- workspace subagents (RESOURCES_PLAN Phase 2) ---


@router.get("/api/workspaces/{workspace_id}/subagents")
def list_workspace_subagents(
    workspace_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
):
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


@router.put("/api/workspaces/{workspace_id}/subagents")
def replace_workspace_subagents(
    workspace_id: str,
    body: ReplaceSubagents,
    store: Annotated[SessionStore, Depends(get_store)],
):
    try:
        items = store.replace_workspace_subagents(
            workspace_id,
            [s.model_dump() for s in body.subagents],
            actor=body.actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Phase 1: re-materialize subagent files after the DB write.
    with contextlib.suppress(Exception):
        sync_workspace_by_name(store, get_settings(), workspace_id)
    return {"items": items}


# ---------------------------------------------------------------------------
# Workspace skill bindings — dedicated surface for skill-type resources
# (kept separate from generic resources to give the UI a simple bind/unbind
# toggle that doesn't expose target_path, materialize_mode, etc.).
# ---------------------------------------------------------------------------


class ReplaceSkillBindings(BaseModel):
    skill_resource_ids: list[str] = Field(default_factory=list)
    reason: str = "skill bindings update"
    actor: str | None = None


@router.get("/api/workspaces/{workspace_id}/skill-bindings")
def list_workspace_skill_bindings(
    workspace_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
):
    """Return every skill-type resource in the catalog with a ``bound`` flag.

    The shape is `{items: [{...resource, bound: bool}]}` so the UI can
    render a single list of checkboxes without joining two endpoints.
    """
    catalog = store.list_repo_resources(type="skill", limit=500)
    current = store.list_workspace_file_bindings(workspace_id)
    bound_ids: set[str] = set()
    for b in current:
        resource = store.get_repo_resource(b["resource_id"])
        if resource and resource.get("type") == "skill":
            bound_ids.add(b["resource_id"])
    items = []
    for r in catalog:
        items.append({**r, "bound": r["id"] in bound_ids})
    return {"items": items}


@router.put("/api/workspaces/{workspace_id}/skill-bindings")
def replace_workspace_skill_bindings(
    workspace_id: str,
    body: ReplaceSkillBindings,
    store: Annotated[SessionStore, Depends(get_store)],
):
    """Replace the workspace's skill bindings with the given resource set.

    Non-skill bindings (documents/folders/schemas/scripts) are preserved.
    After the DB write, the workspace is re-synced so SKILL.md files
    appear under ``.claude/skills/<name>/`` immediately.
    """
    try:
        items = store.replace_workspace_skill_bindings(
            workspace_id,
            body.skill_resource_ids,
            reason=body.reason,
            actor=body.actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    with contextlib.suppress(Exception):
        sync_workspace_by_name(store, get_settings(), workspace_id)
    return {"items": items}
