"""Agent prompt preview — read-only snapshot of bundle composition.

Used by both the REST `/api/agents/{agent_id}/prompt-resources/preview`
route and the `preview_prompt` MCP tool. Returns the fully composed
prompt plus a per-piece character breakdown and the resolution
snapshot — so callers can see exactly how many chars each appended
resource contributes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import tomllib
from dataclasses import dataclass
from pathlib import Path

from jsonschema.exceptions import SchemaError

from agentbox.core.data.schema_validation import load_json_schema
from agentbox.core.agents.composition.rendering import (
    append_input_schema,
    append_schema,
)
from agentbox.core.data.payload_types import (
    CharBreakdownPart,
    JsonSchemaDict,
    PromptBindingSpec,
    ReferenceMetaView,
    ResolvedBindingView,
    SchemaSlotView,
)
from agentbox.core.data.rows import AgentPromptBindingRow
from agentbox.core.db import (
    AgentVersionManager,
    ResourceBlobManager,
    ResourceManager,
    ResourceVersionManager,
    AgentPromptResourceBindingManager,
)
from agentbox.core.data.payload_types import PromptPreviewResult
from agentbox.core.data.constants import BundleFile
from agentbox.core.agents.composition.rendering import render_for_type
from agentbox.core.agents.composition.resolver import resolve_prompt
from agentbox.core.agents.composition.composer import (
    BaseSegment,
    CompositionDiagnostics,
    InputSchemaSegment,
    OutputSchemaSegment,
    PromptComposition,
    ReferenceSegment,
)

logger = logging.getLogger(__name__)


# ── Exceptions ─────────────────────────────────────────────────────


class PreviewError(Exception):
    """Raised when a binding cannot be resolved (missing resource/version)."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


# ── Preview data types ─────────────────────────────────────────────


@dataclass(frozen=True)
class ReferencePreview:
    """One reference file as exposed in a composition preview."""

    path: str
    heading: str
    content: str


@dataclass(frozen=True)
class CompositionPreview:
    """Read-only snapshot of a bundle's [composition] block.

    Unlike ``compose()``, this returns raw file contents without template
    substitution — suitable for showing the user what the bundle declares.
    """

    system: str
    user_template: str | None
    references: list[ReferencePreview]
    output_schema: JsonSchemaDict | None
    input_schema: JsonSchemaDict | None = None


# ── Helpers for agent prompt preview ───────────────────────────────


def _resolve_binding(
    resources: ResourceManager,
    resource_versions: ResourceVersionManager,
    resource_blobs: ResourceBlobManager,
    b: PromptBindingSpec,
) -> ResolvedBindingView:
    resource_id = b["resource_id"]
    resource = resources.get_resource(resource_id)
    if not resource:
        raise PreviewError(
            "resource_not_found", f"resource {resource_id!r} not found"
        )
    version_id = b.get("pinned_version_id")
    if not version_id:
        active = resource_versions.get_active_version(resource_id)
        if not active:
            raise PreviewError(
                "no_active_version",
                f"resource {resource_id!r} has no active version",
            )
        version_id = active["id"]
    version_id = str(version_id)
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


def _schema_for_slot(resolved: list[ResolvedBindingView], slot: str) -> SchemaSlotView | None:

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



def _append_schema_slot(
    composed: str,
    slot: str,
    schema_view: SchemaSlotView | None,
) -> tuple[str, int]:
    """Append the schema block for *slot* to *composed* using the canonical
    runtime assembler (``rendering.append_input_schema`` /
    ``rendering.append_schema``).

    Returns ``(new_composed, chars_added)`` where ``chars_added`` counts the
    separator ``\\n\\n`` plus the block — matching the ``+2`` convention used
    in the char-breakdown table.  Returns the unchanged *composed* and 0 when
    the view is absent or its text is empty.

    Using the runtime assembler here (rather than a local re-implementation)
    ensures that the schema text appended during preview is byte-identical to
    what ``bundle.compose_from_source`` appends at runtime — single source of
    truth for the append order and formatting.
    """
    if not schema_view or not schema_view.get("text"):
        return composed, 0
    text = schema_view["text"]
    parsed: JsonSchemaDict | None
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        parsed = None
    prev_rstripped_len = len(composed.rstrip())
    if isinstance(parsed, dict):
        if slot == "input_schema":
            composed = append_input_schema(composed, parsed)
        else:
            composed = append_schema(composed, parsed)
    else:
        # Fallback for malformed / non-dict schema content: raw JSON fence.
        # Matches the historical _schema_block fallback text so existing
        # callers see the same output.
        header = "# Input Format" if slot == "input_schema" else "# Required Output"
        block_fb = f"{header}\n\n## JSON Schema\n\n```json\n{text}\n```"
        composed = composed.rstrip() + "\n\n" + block_fb
    chars_added = len(composed) - prev_rstripped_len
    return composed, chars_added


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ── Bundle file preview (disk-based) ───────────────────────────────


def preview(
    bundle_path: Path,
    shared_roots: dict[str, Path],
) -> CompositionPreview:
    """Load a bundle's [composition] block as raw, un-rendered content.

    Args:
        bundle_path: Path to the agent bundle directory.
        shared_roots: Mapping of shared root keys to absolute paths for
            resolving ``shared://<key>/...`` reference paths.

    Returns:
        ``CompositionPreview`` with raw system markdown, raw user template
        (if any), each reference's content, and the output schema JSON
        (if the bundle declares ``output_schema``).
    """

    bundle_path = bundle_path.resolve()
    agent_toml = bundle_path / "agent.toml"
    if not agent_toml.exists():
        raise FileNotFoundError(f"Bundle missing agent.toml: {bundle_path}")
    with agent_toml.open("rb") as f:
        config = tomllib.load(f)
    composition = config.get("composition") or {}

    system_rel = composition.get("system") or composition.get(
        "system_prompt", BundleFile.SYSTEM_PROMPT
    )
    system_path = bundle_path / system_rel
    system_text = _read_text(system_path) if system_path.exists() else ""

    user_template_rel = composition.get("user_template")
    user_template_text: str | None = None
    if user_template_rel:
        user_path = bundle_path / user_template_rel
        if user_path.exists():
            user_template_text = _read_text(user_path)

    refs: list[ReferencePreview] = []
    for ref in composition.get("references", []):
        ref_path_str = ref["path"] if isinstance(ref, dict) else str(ref)
        if ref_path_str.startswith("shared://"):
            rest = ref_path_str[len("shared://") :]
            key, _, rel = rest.partition("/")
            root = shared_roots.get(key)
            if root is None:
                continue
            ref_file = root / rel
        else:
            ref_file = bundle_path / ref_path_str
        if not ref_file.exists():
            continue
        heading = (
            ref.get("heading") if isinstance(ref, dict) and ref.get("heading") else None
        ) or ref_file.stem
        refs.append(
            ReferencePreview(
                path=ref_path_str,
                heading=heading,
                content=_read_text(ref_file),
            )
        )

    schema: JsonSchemaDict | None = None
    output_schema_rel = composition.get("output_schema")
    schema_file: Path | None = None
    if output_schema_rel:
        schema_file = bundle_path / output_schema_rel
    else:
        for sibling_name in (BundleFile.OUTPUT_SCHEMA, BundleFile.OUTPUT_SCHEMA_ALT):
            sibling = bundle_path / sibling_name
            if sibling.exists():
                schema_file = sibling
                break
    if schema_file is not None and schema_file.exists():
        try:
            schema = load_json_schema(_read_text(schema_file))
        except (json.JSONDecodeError, SchemaError):
            schema = None

    input_schema: JsonSchemaDict | None = None
    input_schema_file = bundle_path / BundleFile.INPUT_SCHEMA
    if input_schema_file.exists():
        try:
            input_schema = load_json_schema(_read_text(input_schema_file))
        except (json.JSONDecodeError, SchemaError):
            input_schema = None

    return CompositionPreview(
        system=system_text,
        user_template=user_template_text,
        references=refs,
        output_schema=schema,
        input_schema=input_schema,
    )


# ── Main render_agent_prompt_preview ───────────────────────────────


def _spec_from_row(row: AgentPromptBindingRow) -> PromptBindingSpec:
    return {
        "id": row["id"],
        "resource_id": row["resource_id"],
        "marker": row["marker"],
        "mode": row["mode"],
        "slot": row["slot"],
        "attach_as_reference": row["attach_as_reference"],
        "pinned_version_id": row["pinned_version_id"],
        "display_order": row["display_order"],
        "required": row["required"],
    }


def render_agent_prompt_preview(
    agent_versions: AgentVersionManager,
    resource_versions: ResourceVersionManager,
    resource_blobs: ResourceBlobManager,
    resources: ResourceManager,
    agent_prompt_resource_bindings: AgentPromptResourceBindingManager,
    *,
    agent_id: str,
    template: str | None = None,
    bindings_override: list[PromptBindingSpec] | None = None,
) -> PromptPreviewResult:
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
    if template is None:
        row = agent_versions.get_effective_active(agent_id)
        if row is None:
            raise PreviewError(
                "no_agent_version",
                f"no prompt version for agent {agent_id!r}",
            )
        template = row.get("prompt_content") or ""

    if bindings_override is not None:
        raw: list[PromptBindingSpec] = [
            {**b, "id": b.get("id") or f"preview-{i}"}
            for i, b in enumerate(bindings_override)
        ]
    else:
        raw = [
            _spec_from_row(row)
            for row in agent_prompt_resource_bindings.list_for_agent(agent_id)
        ]

    resolved = [_resolve_binding(resources, resource_versions, resource_blobs, b) for b in raw]

    # DB-as-source-of-truth: ``agent_versions.prompt_content`` (passed in
    # as ``template``) is the only system-prompt source. Legacy
    # ``slot='system'`` bindings are ignored at render time — they remain
    # in the table for history but never shadow live ``edit_prompt`` edits.
    splice_bindings = [b for b in resolved if b.get("marker") and b.get("mode")]
    result = resolve_prompt(template, splice_bindings)

    base_prompt = result.rendered_prompt

    input_schema = _schema_for_slot(resolved, "input_schema")
    output_schema = _schema_for_slot(resolved, "output_schema")
    raw_text_output = output_schema is None

    # ── Build segments for the composer ──────────────────────────────────────
    # Text assembly is delegated to PromptComposition so the references
    # header (Q1: "## References\n\n") and all block formatting are produced
    # by a single code path. The validators-hint block is intentionally absent
    # (Q2: it was preview-only and never reached the model).
    segments: list[BaseSegment | InputSchemaSegment | ReferenceSegment | OutputSchemaSegment] = [
        BaseSegment(text=base_prompt)
    ]

    if input_schema and input_schema.get("text"):
        try:
            parsed_input = load_json_schema(input_schema["text"])
            segments.append(InputSchemaSegment(schema=parsed_input))
        except (TypeError, ValueError, SchemaError):
            pass

    refs_meta: list[ReferenceMetaView] = []
    for b in resolved:
        if not b.get("attach_as_reference") or b.get("slot"):
            continue
        if b["type"] not in ("document", "folder"):
            continue
        rendered = render_for_type(b["type"], b.get("blobs") or [])
        heading = b.get("display_name") or b.get("resource_slug") or b["resource_id"]
        body = rendered.get("text") or ""
        if body:
            segments.append(
                ReferenceSegment(path=b["resource_id"], heading=heading, content=body)
            )
        refs_meta.append(
            {
                "binding_id": b["binding_id"],
                "resource_id": b["resource_id"],
                "version_id": b["version_id"],
                "display_name": b.get("display_name"),
            }
        )

    if output_schema and output_schema.get("text"):
        try:
            parsed_output = load_json_schema(output_schema["text"])
            schema_sha = hashlib.sha256(
                output_schema["text"].encode()
            ).hexdigest()
            segments.append(
                OutputSchemaSegment(schema=parsed_output, schema_sha=schema_sha)
            )
        except (TypeError, ValueError, SchemaError):
            pass

    composition = PromptComposition(
        segments=tuple(segments),
        diagnostics=CompositionDiagnostics(
            unresolved_markers=result.unresolved_markers,
            warnings=result.warnings,
        ),
        bundle_sha="",  # not needed for preview
        user="",
    )
    composed = composition.text

    # ── Build binding-aware char breakdown ────────────────────────────────────
    # The composer's to_preview_result() breakdown omits binding IDs; the
    # preview surface exposes them for UI charting. We build our own here
    # using the same segment traversal but attaching DB-sourced IDs.
    ref_segs = composition.references
    parts: list[CharBreakdownPart] = [
        {"label": "prompt template", "chars": len(base_prompt)},
    ]

    if input_schema and input_schema.get("text"):
        try:
            parsed_input_for_chars = load_json_schema(input_schema["text"])
            block = append_input_schema("", parsed_input_for_chars)
            parts.append(
                {
                    "label": "input_schema block",
                    "chars": len(block) + 2,
                    "binding_id": input_schema["binding_id"],
                    "resource_id": input_schema["resource_id"],
                    "version_id": input_schema["version_id"],
                }
            )
        except (TypeError, ValueError, SchemaError):
            pass

    if ref_segs:
        # Build per-reference chars (first absorbs the "## References\n\n" header).
        ref_binding_map = {
            b["resource_id"]: b
            for b in resolved
            if b.get("attach_as_reference") and not b.get("slot")
            and b["type"] in ("document", "folder")
        }
        for i, seg in enumerate(ref_segs):
            section = seg.render_section()
            chars = len(section) + 2
            if i == 0:
                chars += len("## References\n\n")
            b = ref_binding_map.get(seg.path)
            entry: CharBreakdownPart = {
                "label": seg.heading,
                "chars": chars,
            }
            if b:
                entry["binding_id"] = b["binding_id"]
                entry["resource_id"] = b["resource_id"]
                entry["version_id"] = b["version_id"]
            parts.append(entry)

    if output_schema and output_schema.get("text"):
        try:
            parsed_output_for_chars = load_json_schema(output_schema["text"])
            block = append_schema("", parsed_output_for_chars)
            parts.append(
                {
                    "label": "validator: output schema (json-schema gate)",
                    "kind": "validator",
                    "chars": len(block) + 2,
                    "binding_id": output_schema["binding_id"],
                    "resource_id": output_schema["resource_id"],
                    "version_id": output_schema["version_id"],
                }
            )
        except (TypeError, ValueError, SchemaError):
            pass

    return {
        "rendered_prompt": composed,
        "base_prompt": base_prompt,
        "template": template,
        "unresolved_markers": result.unresolved_markers,
        "warnings": result.warnings,
        "references": refs_meta,
        "input_schema": input_schema,
        "output_schema": output_schema,
        "validation": None,
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


__all__ = [
    "PreviewError",
    "ReferencePreview",
    "CompositionPreview",
    "preview",
    "render_agent_prompt_preview",
]
