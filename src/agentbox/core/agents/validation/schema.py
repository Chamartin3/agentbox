"""Schema resolution and validation result types."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from agentbox.core.agents.config import PythonAgentConfig

# Engine label for the validator that produced the verdict. ``off`` means
# no schema is configured and validation was skipped; ``none`` means a
# schema was expected but the input was unrunnable (empty / unparseable).
ValidationEngine = Literal[
    "jsonschema",
    "pydantic",
    "both",
    "json-schema",
    "http-callback",
    "script",
    "json-schema+http-callback",
    "json-schema+script",
    "none",
    "off",
]


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of validating a backend run's output.

    ``ok=True, engine="off"`` is the no-schema-configured case — the
    executor should treat it as "validation skipped", not "passed".
    """

    ok: bool
    error: str = ""
    engine: ValidationEngine = "off"


def resolve_schema(
    agent: Any,
    workdir: Path,
    project_root: Path | None = None,
    composed_schema: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, str]:
    """Locate the agent's output schema.

    Returns ``(schema_dict, error_msg)`` — ``schema_dict`` is ``None`` when
    no schema is configured (caller should treat the run as no-validation),
    or when the schema file is missing/unreadable (caller should surface
    ``error_msg`` as a validation failure).

    Resolution order:
      1. ``composed_schema`` (already-rendered binding from the prompt
         composer / output-schema prompt-binding).
      2. ``python.output_schema_path`` (legacy file-based contract).
    """
    if isinstance(composed_schema, dict):
        return composed_schema, ""

    python_cfg = PythonAgentConfig.from_agent(agent)
    schema_rel = python_cfg.output_schema_path
    if not schema_rel:
        return None, ""

    schema_path = workdir / schema_rel
    if not schema_path.exists() and project_root is not None:
        schema_path = project_root / schema_rel
    if not schema_path.exists():
        return None, f"schema file not found: {schema_rel}"

    try:
        return json.loads(schema_path.read_text(encoding="utf-8")), ""
    except (json.JSONDecodeError, OSError) as exc:
        return None, f"cannot load schema: {exc}"


__all__ = ["ValidationEngine", "ValidationResult", "resolve_schema"]
