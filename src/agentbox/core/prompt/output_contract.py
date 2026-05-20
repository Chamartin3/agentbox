"""Unified renderer for the ``output_config`` system-prompt fragment.

Phase 2 of the validation-callback migration (see
``docs/plans/validation-callback-architecture.md``). The new
``config_json["output"]`` block carries three optional pieces that must
appear in every agent's system prompt the same way regardless of which
backend will run it:

1. ``json_schema`` — Gate-1 structural contract.
2. ``rules``      — plain-English constraints JSON Schema can't express.
3. ``validator``  — Gate-2 HTTP callback (rendered as a short hint).

Rendering lives in one place here so the token backend (pydantic-ai)
and the file/string backends (claude_code, opencode, codex) produce
byte-identical fragments. Drift between backends has historically
caused silent contract divergence; this module is the single source
of truth.
"""

from __future__ import annotations

import json

from agentbox.core.agent.config import OutputConfig


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
            "```json\n"
            + json.dumps(output_config.json_schema, indent=2)
            + "\n```"
        )

    # Plan 22: validators carry their own constraint text (description).
    # Build the Constraints bullets from each validator's description.
    # Legacy fallback: if no validator carries a description AND the
    # contract still has rules[], render those bullets instead. This
    # fallback gets dropped in Plan 22 / Phase 3 once migrations land.
    validator_bullets = [
        v.description.strip()
        for v in output_config.validators
        if getattr(v, "description", "").strip()
    ]
    if validator_bullets:
        parts.append("## Constraints")
        parts.append("\n".join(f"- {b}" for b in validator_bullets))
    elif output_config.rules:
        parts.append("## Constraints")
        parts.append("\n".join(f"- {rule}" for rule in output_config.rules))

    return "\n\n".join(parts).rstrip()


def append(text: str, output_config: OutputConfig) -> str:
    """Append the rendered block to ``text`` with one blank line separator."""
    block = render(output_config)
    if not block:
        return text
    base = (text or "").rstrip()
    return f"{base}\n\n{block}" if base else block


__all__ = ["append", "render"]
