"""Internal helper functions for the preview renderer."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from agentbox.core.agents.config import (
    HttpValidatorConfig,
    OutputConfig,
    ScriptValidatorConfig,
)
from agentbox.core.agents.composition.bundle import _append_input_schema, _append_schema
from agentbox.core.agents.composition.output_contract import render as _render_output_contract
from agentbox.core.agents.composition.rendering import render_for_type

if TYPE_CHECKING:
    from agentbox.core.db import (
        AgentVersionManager,
        ResourceBlobManager,
        ResourceManager,
        ResourceVersionManager,
    )


class PreviewError(Exception):
    """Raised when a binding cannot be resolved (missing resource/version)."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _resolve_binding(
    resources: ResourceManager,
    resource_versions: ResourceVersionManager,
    resource_blobs: ResourceBlobManager,
    b: dict,
) -> dict:
    resource = resources.get_resource(b["resource_id"])
    if not resource:
        raise PreviewError(
            "resource_not_found", f"resource {b['resource_id']!r} not found"
        )
    version_id = b.get("pinned_version_id")
    if not version_id:
        active = resource_versions.get_active_version(b["resource_id"])
        if not active:
            raise PreviewError(
                "no_active_version",
                f"resource {b['resource_id']!r} has no active version",
            )
        version_id = active["id"]
    version = resource_versions.get_version(version_id)
    if not version:
        raise PreviewError(
            "no_version", f"version {version_id!r} not found"
        )
    blobs = list(resource_blobs.iter_blobs(version_id))
    return {
        "binding_id": b.get("id") or b.get("binding_id") or "live",
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
    parts: list[str] = []
    refs_meta: list[dict] = []
    per_ref_chars: list[dict] = []
    for b in resolved:
        if not b.get("attach_as_reference") or b.get("slot"):
            continue
        if b["type"] not in ("document", "folder"):
            continue
        rendered = render_for_type(b["type"], b.get("blobs") or [])
        heading = b.get("display_name") or b.get("resource_slug") or b["resource_id"]
        body = rendered.get("text") or ""
        if body:
            entry = f"## {heading}\n\n{body}"
            parts.append(entry)
            per_ref_chars.append(
                {
                    "label": heading,
                    "chars": len(entry) + 2,
                    "binding_id": b["binding_id"],
                    "resource_id": b["resource_id"],
                    "version_id": b["version_id"],
                }
            )
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


def _validation_block_for_preview(
    agent_versions: AgentVersionManager,
    resources: ResourceManager,
    agent_id: str,
) -> tuple[str, dict | None]:
    """Render the validators hint block from the agent's inline
    ``config_json["output"].validators`` on the active version.

    Schema is intentionally NOT rendered here — it already appears as
    the output_schema block above (single source of truth: the binding).
    Returns ``(rendered_text, view_dict)`` where view_dict is the
    structured payload returned to the UI under ``validation``.
    """
    active = agent_versions.get_active(agent_id)
    if not active or active.get("id") is None:
        return "", None
    raw_cfg = active.get("config_json")
    if isinstance(raw_cfg, str):
        try:
            cfg = json.loads(raw_cfg)
        except (ValueError, TypeError):
            cfg = {}
    elif isinstance(raw_cfg, dict):
        cfg = raw_cfg
    else:
        cfg = {}
    output_section = cfg.get("output") if isinstance(cfg, dict) else None
    entries = (
        output_section.get("validators") if isinstance(output_section, dict) else None
    )
    if not isinstance(entries, list) or not entries:
        return "", None
    validators_meta: list[dict] = []
    runtime_validators: list = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        kind = entry.get("kind")
        description = entry.get("description") or ""
        if not isinstance(description, str):
            description = ""
        if kind == "http":
            validators_meta.append(
                {
                    "kind": "http",
                    "endpoint": entry.get("endpoint", ""),
                    "timeout_seconds": int(entry.get("timeout_seconds", 5)),
                    "description": description,
                }
            )
            runtime_validators.append(
                HttpValidatorConfig(
                    kind="http",
                    endpoint=entry.get("endpoint", ""),
                    timeout_seconds=int(entry.get("timeout_seconds", 5)),
                    description=description,
                )
            )
        elif kind == "script":
            rid = entry.get("resource_id", "")
            resource = resources.get_resource(rid) if rid else None
            validators_meta.append(
                {
                    "kind": "script",
                    "resource_id": rid,
                    "resource_slug": (resource or {}).get("slug"),
                    "resource_display_name": (resource or {}).get("display_name"),
                    "pinned_version_id": entry.get("pinned_version_id"),
                    "description": description,
                }
            )
            runtime_validators.append(
                ScriptValidatorConfig(
                    kind="script",
                    resource_id=rid,
                    resource_version_id=entry.get("pinned_version_id"),
                    source_code="",
                    description=description,
                )
            )
    if not runtime_validators:
        return "", None
    rendered = _render_output_contract(
        OutputConfig(
            json_schema=None,
            validators=tuple(runtime_validators),
        )
    )
    view = {
        "validators": validators_meta,
    }
    return rendered, view


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
    header = "# Input Format" if slot == "input_schema" else "# Required Output"
    return f"{header}\n\n## JSON Schema\n\n```json\n{text}\n```"
