"""Shared prompt composition for all backend generators.

The PromptComposer assembles the canonical prompt text from composed metadata.
Each backend generator reads the resulting markdown asset files rather than
rebuilding the prompt inline.

Produces three canonical files under ``prompts/``:

- ``system.md``        — The system prompt (already composed with references).
- ``user.md``          — The user message / variables payload.
- ``schema.json``      — Output JSON schema.
- ``full_prompt.md``   — Assembled full prompt (system + schema + user) for
  backends that need a single file.

Backends should read from these shared assets instead of reconstructing
the prompt themselves.  This ensures every backend sees the exact same
composed text.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class PromptComposer:
    """Assemble canonical prompt markdown assets from composed metadata."""

    @staticmethod
    def write_prompts(prompt_dir: Path, composed: Any) -> None:
        """Write all canonical prompt files into ``prompt_dir``.

        ``composed`` is a :class:`ComposedMetadata` instance.
        """
        prompt_dir.mkdir(parents=True, exist_ok=True)

        system_path = prompt_dir / "system.md"
        if not system_path.exists():
            system_path.write_text(composed.system, encoding="utf-8")

        user_path = prompt_dir / "user.md"
        if not user_path.exists():
            user_path.write_text(composed.user, encoding="utf-8")

        if composed.schema is not None:
            schema_path = prompt_dir / "schema.json"
            if not schema_path.exists():
                schema_path.write_text(
                    json.dumps(composed.schema, indent=2), encoding="utf-8"
                )

        full_path = prompt_dir / "full_prompt.md"
        if not full_path.exists():
            full_text = PromptComposer.assemble_full_prompt(composed)
            full_path.write_text(full_text, encoding="utf-8")

    @staticmethod
    def assemble_full_prompt(composed: Any) -> str:
        """Assemble the complete prompt as a single markdown document.

        Returns a markdown string containing:
        1. System instructions
        2. Required output format + JSON schema (if present)
        3. Task input (if present)
        """
        parts: list[str] = ["# System Instructions", composed.system]

        if composed.schema is not None:
            parts.extend(
                [
                    "",
                    "# Required Output",
                    (
                        "Respond with a SINGLE JSON object that strictly conforms to the "
                        "schema below. Output ONLY the JSON object — no prose, no "
                        "markdown fences, no commentary before or after."
                    ),
                    "",
                    "## JSON Schema",
                    "```json",
                    json.dumps(composed.schema, indent=2),
                    "```",
                ]
            )

        if composed.user:
            parts.extend(
                [
                    "",
                    "# Task Input",
                    "```json",
                    composed.user,
                    "```",
                ]
            )

        return "\n\n".join(parts)

    @staticmethod
    def read_full_prompt(prompt_dir: Path) -> str:
        """Read the pre-assembled full prompt."""
        full_path = prompt_dir / "full_prompt.md"
        return full_path.read_text(encoding="utf-8")

    @staticmethod
    def read_system_prompt(prompt_dir: Path) -> str:
        """Read the system prompt."""
        return (prompt_dir / "system.md").read_text(encoding="utf-8")

    @staticmethod
    def read_user_message(prompt_dir: Path) -> str:
        """Read the user message."""
        return (prompt_dir / "user.md").read_text(encoding="utf-8")

    @staticmethod
    def read_schema(prompt_dir: Path) -> dict[str, Any] | None:
        """Read the output schema as a dict."""
        schema_path = prompt_dir / "schema.json"
        if not schema_path.exists():
            return None
        return json.loads(schema_path.read_text(encoding="utf-8"))
