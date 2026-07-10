"""Prompt-text rendering for the composer.

Two families of renderers, both turning something into prompt text:

1. **Resource embeds** (``render_document`` / ``render_folder_manifest`` /
   ``render_skill_primer`` / ``render_schema`` / ``render_script`` /
   ``render_for_type``) — render a bound resource version for splicing into
   a prompt. Return a ``RenderedBlob`` (``text`` + ``metadata``).

2. **Output-contract fragments** (``render`` / ``append`` /
   ``append_input_schema`` / ``append_schema`` /
   ``append_validation_engine_hint``) — turn the *validation contract*
   (``OutputConfig`` / input+output schema / validation-engine hint) into
   system-prompt text. ``core.agents.contract`` owns declaring and checking
   that contract; rendering it INTO the prompt is a composition concern and
   lives here. One place so every backend produces byte-identical fragments.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from agentbox.core.agents.contract.schema import OutputConfig
from agentbox.core.data.payload_types import JsonSchemaDict, RenderedBlob
from agentbox.core.data.rows import ResourceBlobRow

SKILL_ENTRY = "SKILL.md"


def _blob_text(blob: ResourceBlobRow) -> str:
    text = blob.get("content_text")
    if text:
        return text
    content = blob.get("content")
    if isinstance(content, (bytes, bytearray)):
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            return ""
    if isinstance(content, str):
        return content
    return ""


def render_document(blobs: Iterable[ResourceBlobRow]) -> RenderedBlob:
    blobs = list(blobs)
    body = _blob_text(blobs[0]) if blobs else ""
    return {"text": body, "metadata": {"role": "document"}}


def render_folder_manifest(blobs: Iterable[ResourceBlobRow]) -> RenderedBlob:
    blobs = list(blobs)
    paths = [b["relative_path"] for b in blobs if b.get("relative_path")]
    text = "\n".join(f"- {p}" for p in sorted(paths))
    return {
        "text": text,
        "metadata": {"role": "folder_manifest", "file_count": len(paths)},
    }


def render_skill_primer(blobs: Iterable[ResourceBlobRow]) -> RenderedBlob:
    blobs = list(blobs)
    entry = next((b for b in blobs if b.get("relative_path") == SKILL_ENTRY), None)
    if entry is None:
        return {"text": "", "metadata": {"role": "skill_primer", "missing_entry": True}}
    return {
        "text": _blob_text(entry),
        "metadata": {
            "role": "skill_primer",
            "entry_path": SKILL_ENTRY,
            "file_count": len(blobs),
        },
    }


def render_schema(blobs: Iterable[ResourceBlobRow]) -> RenderedBlob:
    blobs = list(blobs)
    body = _blob_text(blobs[0]) if blobs else ""
    return {"text": body, "metadata": {"role": "schema"}}


def render_script(blobs: Iterable[ResourceBlobRow]) -> RenderedBlob:
    blobs = list(blobs)
    body = _blob_text(blobs[0]) if blobs else ""
    return {"text": body, "metadata": {"role": "script"}}


def render_for_type(type: str, blobs: Iterable[ResourceBlobRow]) -> RenderedBlob:
    if type == "document":
        return render_document(blobs)
    if type == "folder":
        return render_folder_manifest(blobs)
    if type == "skill":
        return render_skill_primer(blobs)
    if type == "schema":
        return render_schema(blobs)
    if type == "script":
        return render_script(blobs)
    raise ValueError(f"Unknown resource type for rendering: {type!r}")


# ── output-contract fragments ─────────────────────────────────────────────
# The ``config_json["output"]`` block carries three optional pieces that must
# appear in every agent's system prompt the same way regardless of which
# backend runs it: ``json_schema`` (structural contract), ``rules`` (plain
# constraints), and ``validator`` (rendered as a short hint).


def render(output_config: OutputConfig) -> str:
    """Render the unified output-contract block.

    Returns the empty string when nothing in ``output_config`` is set
    so callers can unconditionally append it to the system prompt.
    """
    parts: list[str] = []

    if isinstance(output_config.json_schema, dict):
        parts.append("# Required Output")
        parts.append(
            "Respond with a SINGLE JSON object that strictly conforms to "
            "the schema below. Output ONLY the JSON object — no prose, no "
            "markdown fences, no commentary before or after."
        )
        parts.append("## JSON Schema")
        parts.append(
            "```json\n" + json.dumps(output_config.json_schema, indent=2) + "\n```"
        )

    # Validators carry their own constraint text (description).
    # Multi-line descriptions explode into one bullet per non-empty line
    # so multi-rule descriptions stay rendered as discrete bullets (not a
    # single multi-line bullet).
    bullets: list[str] = []
    for v in output_config.validators:
        desc = getattr(v, "description", "")
        if not isinstance(desc, str):
            continue
        for line in desc.splitlines():
            stripped = line.strip()
            if stripped:
                bullets.append(stripped)
    if bullets:
        parts.append("## Constraints")
        parts.append("\n".join(f"- {b}" for b in bullets))

    return "\n\n".join(parts).rstrip()


def append(text: str, output_config: OutputConfig) -> str:
    """Append the rendered block to ``text`` with one blank line separator."""
    block = render(output_config)
    if not block:
        return text
    base = (text or "").rstrip()
    return f"{base}\n\n{block}" if base else block


def append_input_schema(text: str, schema: JsonSchemaDict) -> str:
    """Append an input-format instruction block describing ``schema``.

    Goes on the system prompt so the agent learns the shape of the
    incoming payload up-front, before the user message is processed.
    """
    _PROMPTS_DIR = Path(__file__).parent / "prompts"
    _INPUT_SCHEMA_TEMPLATE = (_PROMPTS_DIR / "input_schema.md").read_text(
        encoding="utf-8"
    )

    block = _INPUT_SCHEMA_TEMPLATE.format(schema=json.dumps(schema, indent=2)).rstrip()
    base = (text or "").rstrip()
    return f"{base}\n\n{block}" if base else block


def append_schema(text: str, schema: JsonSchemaDict) -> str:
    """Append a structured-output instruction block referencing ``schema``.

    Agents that declare an output_schema expect their final reply to be a
    single JSON object conforming to that schema. The schema block is
    appended to the system prompt (the durable contract), not the user
    message — that keeps the contract co-located with the agent's role
    instructions and out of the variable user input.

    The instruction text lives in ``prompts/output_schema.md`` so it can be
    edited without code changes.
    """
    _PROMPTS_DIR = Path(__file__).parent / "prompts"
    _OUTPUT_SCHEMA_TEMPLATE = (_PROMPTS_DIR / "output_schema.md").read_text(
        encoding="utf-8"
    )

    block = _OUTPUT_SCHEMA_TEMPLATE.format(schema=json.dumps(schema, indent=2)).rstrip()
    base = (text or "").rstrip()
    return f"{base}\n\n{block}" if base else block


def append_validation_engine_hint(text: str, engine: str) -> str:
    """Append a short note about which validation engine will be enforced.

    This tells the LLM how strictly its output will be checked so it can
    self-correct before emitting.
    """
    hints = {
        "jsonschema": (
            "## Validation\n\nYour output will be validated against the schema "
            "above using JSON Schema. All required fields must be present and "
            "types must match."
        ),
        "pydantic": (
            "## Validation\n\nYour output will be validated using strict "
            "type checking (pydantic). Required fields, string lengths, and "
            "type constraints are enforced — missing or malformed fields will "
            "cause the run to fail."
        ),
        "both": (
            "## Validation\n\nYour output will be validated twice: first "
            "against the JSON Schema above, then through strict type checking "
            "(pydantic). Required fields, string lengths, type constraints, "
            "and structural rules are all enforced — any violation causes "
            "the run to fail."
        ),
    }
    hint = hints.get(engine, hints["both"])
    base = (text or "").rstrip()
    return f"{base}\n\n{hint}" if base else hint


__all__ = [
    "append",
    "append_input_schema",
    "append_schema",
    "append_validation_engine_hint",
    "render",
    "render_document",
    "render_folder_manifest",
    "render_for_type",
    "render_schema",
    "render_script",
    "render_skill_primer",
]
