"""Unified renderer for output-contract system-prompt fragments.

Pulled from ``composition/output_contract.py`` and the 3 helpers from
``bundle/_helpers.py`` (renamed without leading underscores).

The ``config_json["output"]`` block carries three optional pieces that must
appear in every agent's system prompt the same way regardless of which
backend will run it:

1. ``json_schema`` — Gate-1 structural contract.
2. ``rules``      — plain-English constraints JSON Schema can't express.
3. ``validator``  — Gate-2 HTTP callback (rendered as a short hint).

Rendering lives in one place here so the token backend (pydantic-ai)
and the file/string backends (claude_code, opencode, codex) produce
byte-identical fragments. This module is the single source of truth.
"""

from __future__ import annotations

import json
from pathlib import Path

from agentbox.core.agents.contract.schema import OutputConfig
from agentbox.core.data.payload_types import JsonSchemaDict


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
    # Build the Constraints bullets from each validator's description.
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
]
