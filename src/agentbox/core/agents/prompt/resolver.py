"""Resolve `{{resource:<marker>}}` markers in an agent prompt (Plan 02).

Pure function: takes a prompt template and the agent's bindings (with
their resolved blob lists) and returns the spliced prompt plus a
snapshot of which versions were used.

The executor wires this in; this module knows nothing about the DB.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from agentbox.core.agents.prompt.rendering import render_for_type

_MARKER_RE = re.compile(r"\{\{resource:([a-zA-Z0-9_\-]+)\}\}")


@dataclass(frozen=True)
class ResolvedBinding:
    binding_id: str
    marker: str
    resource_id: str
    version_id: str
    content_hash: str
    type: str
    mode: str
    rendered: str
    required: bool


@dataclass(frozen=True)
class PromptResolution:
    rendered_prompt: str
    snapshot: list[ResolvedBinding]
    unresolved_markers: list[str]
    warnings: list[str]


def _render_for_mode(type: str, mode: str, blobs: list[dict], display_name: str) -> str:
    if mode == "name_only":
        return f"- {display_name}"
    if mode == "inline" and type == "document":
        return render_for_type("document", blobs)["text"]
    if mode == "skill_primer" and type == "skill":
        return render_for_type("skill", blobs)["text"]
    if mode == "manifest" and type == "folder":
        return render_for_type("folder", blobs)["text"]
    raise ValueError(f"Mode {mode!r} is not valid for resource type {type!r}")


def resolve_prompt(
    template: str,
    resolved_bindings: Iterable[dict],
) -> PromptResolution:
    """Splice resolved bindings into ``template``.

    Each entry in ``resolved_bindings`` must have:
        binding_id, marker, resource_id, version_id, content_hash,
        type, mode, blobs (list of blob dicts), display_name, required.
    """
    by_marker: dict[str, list[ResolvedBinding]] = {}
    snapshot: list[ResolvedBinding] = []
    warnings: list[str] = []
    for b in resolved_bindings:
        # Schema-slot and other marker-less bindings are not splice
        # candidates — callers must handle them separately. Skip them
        # here so resolve_prompt only deals with marker/mode bindings.
        if not b.get("marker") or not b.get("mode"):
            continue
        try:
            rendered = _render_for_mode(
                b["type"], b["mode"], b.get("blobs") or [], b.get("display_name", "")
            )
        except ValueError as exc:
            if b.get("required"):
                raise
            warnings.append(f"binding {b['binding_id']}: {exc}")
            rendered = ""
        rb = ResolvedBinding(
            binding_id=b["binding_id"],
            marker=b["marker"],
            resource_id=b["resource_id"],
            version_id=b["version_id"],
            content_hash=b["content_hash"],
            type=b["type"],
            mode=b["mode"],
            rendered=rendered,
            required=bool(b.get("required", True)),
        )
        snapshot.append(rb)
        by_marker.setdefault(b["marker"], []).append(rb)

    used_markers: set[str] = set()
    unresolved: list[str] = []

    def _replace(match: re.Match) -> str:
        marker = match.group(1)
        used_markers.add(marker)
        items = by_marker.get(marker)
        if not items:
            unresolved.append(marker)
            return ""
        return "\n\n".join(item.rendered for item in items if item.rendered)

    rendered = _MARKER_RE.sub(_replace, template)

    # Bindings declared but never referenced by a marker — warn.
    for marker, items in by_marker.items():
        if marker not in used_markers:
            for item in items:
                if item.required:
                    warnings.append(
                        f"binding {item.binding_id}: marker {marker!r} not found in prompt"
                    )

    return PromptResolution(
        rendered_prompt=rendered,
        snapshot=snapshot,
        unresolved_markers=unresolved,
        warnings=warnings,
    )
