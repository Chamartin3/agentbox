"""Shared agent-prompt preview renderer.

Used by both the REST `/api/agents/{agent_id}/prompt-resources/preview`
route and the `preview_prompt` MCP tool. Returns the fully composed
prompt plus a per-piece character breakdown and the resolution
snapshot — so callers can see exactly how many chars each appended
resource contributes.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from agentbox.core.agent.config import (
    HttpValidatorConfig,
    OutputConfig,
    ScriptValidatorConfig,
)
from agentbox.core.agent.prompt.composition import _append_input_schema, _append_schema
from agentbox.core.agent.prompt.output_contract import render as _render_output_contract
from agentbox.core.agent.prompt.rendering import render_for_type
from agentbox.core.agent.prompt.resolver import resolve_prompt

if TYPE_CHECKING:
    from agentbox.core.data import SessionStore


class PreviewError(Exception):
    """Raised when a binding cannot be resolved (missing resource/version)."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _resolve_binding(store: SessionStore, b: dict) -> dict:
    resource = store.get_repo_resource(b["resource_id"])
    if not resource:
        raise PreviewError(
            "resource_not_found", f"resource {b['resource_id']!r} not found"
        )
    version_id = b.get("pinned_version_id")
    if not version_id:
        active = store.get_active_repo_version(b["resource_id"])
        if not active:
            raise PreviewError(
                "no_active_version",
                f"resource {b['resource_id']!r} has no active version",
            )
        version_id = active["id"]
    version = store.get_repo_version(version_id)
    if not version:
        raise PreviewError(
            "no_version", f"version {version_id!r} not found"
        )
    blobs = list(store.iter_repo_blobs(version_id))
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
    store: SessionStore, agent_id: str
) -> tuple[str, dict | None]:
    """Render the validators hint block from the agent's inline
    ``config_json["output"].validators`` on the active version.

    Schema is intentionally NOT rendered here — it already appears as
    the output_schema block above (single source of truth: the binding).
    Returns ``(rendered_text, view_dict)`` where view_dict is the
    structured payload returned to the UI under ``validation``.
    """
    active = store.get_active_version(agent_id)
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
            resource = store.get_repo_resource(rid) if rid else None
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


def render_agent_prompt_preview(
    store: SessionStore,
    *,
    agent_id: str,
    template: str,
    bindings_override: list[dict] | None = None,
) -> dict:
    """Render the full composed prompt for an agent.

    If ``bindings_override`` is provided, use it instead of the live
    ``agent_prompt_resource_bindings`` rows for the agent. The override
    list uses the same shape as the input to ``replace_prompt_bindings``.

    On success returns a dict with keys:
        rendered_prompt, base_prompt, template, unresolved_markers,
        warnings, references, input_schema, output_schema,
        raw_text_output, char_breakdown, total_chars, snapshot.

    On binding-resolution failure raises ``PreviewError``.
    """
    if bindings_override is not None:
        raw = [
            {**b, "id": b.get("id") or f"preview-{i}"}
            for i, b in enumerate(bindings_override)
        ]
    else:
        raw = store.list_prompt_bindings(agent_id)

    resolved = [_resolve_binding(store, b) for b in raw]

    # DB-as-source-of-truth: ``agent_versions.prompt_content`` (passed in
    # as ``template``) is the only system-prompt source. Legacy
    # ``slot='system'`` bindings are ignored at render time — they remain
    # in the table for history but never shadow live ``edit_prompt`` edits.
    splice_bindings = [b for b in resolved if b.get("marker") and b.get("mode")]
    result = resolve_prompt(template, splice_bindings)

    refs_text, refs_meta, per_ref_chars = _render_references_block(resolved)
    base_prompt = result.rendered_prompt
    composed = base_prompt

    input_schema = _schema_for_slot(resolved, "input_schema")
    output_schema = _schema_for_slot(resolved, "output_schema")
    raw_text_output = output_schema is None

    input_schema_block = _schema_block("input_schema", input_schema)
    if input_schema_block:
        composed = composed.rstrip() + "\n\n" + input_schema_block

    if refs_text:
        composed = composed.rstrip() + "\n\n" + refs_text

    output_schema_block = _schema_block("output_schema", output_schema)
    if output_schema_block:
        composed = composed.rstrip() + "\n\n" + output_schema_block

    # Validation contract — rules + a short validators hint, mirroring
    # what core/prompt/output_contract.append() does at runtime so the
    # preview reflects what the model actually sees. The schema piece is
    # intentionally omitted (already rendered above from the binding).
    validation_block, validation_view = _validation_block_for_preview(store, agent_id)
    if validation_block:
        composed = composed.rstrip() + "\n\n" + validation_block

    parts: list[dict] = [
        {"label": "prompt template", "chars": len(base_prompt)},
    ]
    if input_schema_block and input_schema is not None:
        parts.append(
            {
                "label": "input_schema block",
                "chars": len(input_schema_block) + 2,
                "binding_id": input_schema["binding_id"],
                "resource_id": input_schema["resource_id"],
                "version_id": input_schema["version_id"],
            }
        )
    if refs_text:
        parts.extend(per_ref_chars)
    # Validator-sourced blocks share the "validator:" prefix so they're
    # visually grouped in the composer breakdown chart — schema (implicit
    # validator), rules, and the validation hint all originate from the
    # validation contract surface.
    if output_schema_block and output_schema is not None:
        parts.append(
            {
                "label": "validator: output schema (json-schema gate)",
                "kind": "validator",
                "chars": len(output_schema_block) + 2,
                "binding_id": output_schema["binding_id"],
                "resource_id": output_schema["resource_id"],
                "version_id": output_schema["version_id"],
            }
        )
    if validation_block:
        parts.append(
            {
                "label": "validator: constraints + post-hoc validators",
                "kind": "validator",
                "chars": len(validation_block) + 2,
            }
        )

    return {
        "rendered_prompt": composed,
        "base_prompt": base_prompt,
        "template": template,
        "unresolved_markers": result.unresolved_markers,
        "warnings": result.warnings,
        "references": refs_meta,
        "input_schema": input_schema,
        "output_schema": output_schema,
        "validation": validation_view,
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
                "chars": len(rb.rendered),
            }
            for rb in result.snapshot
        ],
    }
