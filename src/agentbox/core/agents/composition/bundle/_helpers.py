"""Prompt composition — shared bundle renderer for agentbox and callers.

This module is intentionally HTTP-free and side-effect-free so that caller
projects can import it without pulling in the agentbox server
runtime.

"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_TEMPLATE_VAR_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def _format_template(text: str, variables: dict[str, str]) -> str:
    """Substitute ``{var_name}`` placeholders only.

    Unlike ``str.format``, this leaves every other brace untouched — so
    prompts can embed literal JSON examples (``{"key": value}``) without
    needing them escaped as ``{{ }}``. Only bare identifier placeholders
    matching a known variable key are replaced; unknown ``{name}`` tokens
    are passed through verbatim.
    """
    missing: list[str] = []

    def _sub(m: re.Match[str]) -> str:
        key = m.group(1)
        if key in variables:
            return str(variables[key])
        missing.append(key)
        return m.group(0)

    rendered = _TEMPLATE_VAR_RE.sub(_sub, text)
    if missing:
        raise KeyError(f"Missing template variable {missing[0]!r} in prompt")
    return rendered


_PROMPTS_DIR = Path(__file__).parent.parent / "bundle" / "prompts"
_OUTPUT_SCHEMA_TEMPLATE = (_PROMPTS_DIR / "output_schema.md").read_text(
    encoding="utf-8"
)
_INPUT_SCHEMA_TEMPLATE = (_PROMPTS_DIR / "input_schema.md").read_text(encoding="utf-8")


def _append_input_schema(text: str, schema: dict[str, Any]) -> str:
    """Append an input-format instruction block describing ``schema``.

    Goes on the system prompt so the agent learns the shape of the
    incoming payload up-front, before the user message is processed.
    """
    block = _INPUT_SCHEMA_TEMPLATE.format(schema=json.dumps(schema, indent=2)).rstrip()
    base = (text or "").rstrip()
    return f"{base}\n\n{block}" if base else block


def _append_schema(text: str, schema: dict[str, Any]) -> str:
    """Append a structured-output instruction block referencing ``schema``.

    Agents that declare an output_schema expect their final reply to be a
    single JSON object conforming to that schema. The schema block is
    appended to the system prompt (the durable contract), not the user
    message — that keeps the contract co-located with the agent's role
    instructions and out of the variable user input.

    The instruction text lives in ``prompts/output_schema.md`` so it can be
    edited without code changes.
    """
    block = _OUTPUT_SCHEMA_TEMPLATE.format(schema=json.dumps(schema, indent=2)).rstrip()
    base = (text or "").rstrip()
    return f"{base}\n\n{block}" if base else block


def _append_validation_engine_hint(text: str, engine: str) -> str:
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

def _ref_heading_fallback(path: str) -> str:
    if path.startswith("shared://"):
        tail = path[len("shared://") :].rsplit("/", 1)[-1]
    else:
        tail = path.rsplit("/", 1)[-1]
    stem, _, _ = tail.partition(".")
    return stem or tail

