"""Output validation — shared across executor and backends.

Lifted out of ``executor.py`` so :class:`BackendAdapter` (and any
custom backend) can validate output without depending on the executor.

``validate_output()`` is the public entry point. It resolves the agent's
schema (from ``_composed_schema`` first, then ``runner.output_schema_path``)
and runs the engine declared by ``runner.output_validation_engine``.

Backends that produce already-typed outputs (token / pydantic-ai) can
either call this directly or short-circuit with their own
:class:`ValidationResult`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import jsonschema as _jsonschema

# Engine label for the validator that produced the verdict. ``off`` means
# no schema is configured and validation was skipped; ``none`` means a
# schema was expected but the input was unrunnable (empty / unparseable).
ValidationEngine = Literal["jsonschema", "pydantic", "both", "none", "off"]


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of validating a backend run's output.

    ``ok=True, engine="off"`` is the no-schema-configured case — the
    executor should treat it as "validation skipped", not "passed".
    """

    ok: bool
    error: str = ""
    engine: ValidationEngine = "off"


_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*\n(.*?)\n```", re.DOTALL)


def extract_json(text: str) -> str:
    """Pull a JSON payload out of prose-wrapped model output.

    Models often wrap JSON in ``` fences plus surrounding prose despite
    being told not to. Validation should still engage on the JSON they
    produced, so we extract the first fenced block when present, then
    fall back to the first ``{...}`` / ``[...]`` slice, then return the
    raw text unchanged for ``json.loads`` to fail on naturally.
    """
    if not text:
        return text
    m = _FENCED_JSON_RE.search(text)
    if m:
        return m.group(1).strip()
    s = text.strip()
    if s.startswith(("{", "[")):
        return s
    for opener, closer in (("{", "}"), ("[", "]")):
        i = s.find(opener)
        j = s.rfind(closer)
        if 0 <= i < j:
            return s[i : j + 1]
    return s


def format_jsonschema_error(exc: _jsonschema.ValidationError) -> str:
    """Render a jsonschema error so the agent sees *where* it failed.

    The default ``str(exc)`` dumps the schema + instance but doesn't say
    *which JSON pointer path* the failing validator was anchored at —
    agents reading the error try to fix the wrong place. We surface the
    instance path, schema path, sub-errors for ``oneOf``, and a truncated
    instance preview so the retry prompt is actionable.
    """
    instance_pointer = (
        "/" + "/".join(str(p) for p in exc.absolute_path)
        if exc.absolute_path
        else "/"
    )
    schema_pointer = (
        "/" + "/".join(str(p) for p in exc.absolute_schema_path)
        if exc.absolute_schema_path
        else "/"
    )
    lines = [
        f"validation failed at instance path: {instance_pointer}",
        f"schema rule violated at: {schema_pointer} ({exc.validator})",
        f"message: {exc.message}",
    ]
    if exc.validator == "oneOf" and exc.context:
        lines.append("")
        lines.append("oneOf sub-errors (each branch's first failure):")
        for branch_idx, sub in enumerate(exc.context):
            title = ""
            try:
                title = (
                    sub.schema.get("title", "") if isinstance(sub.schema, dict) else ""
                )
            except AttributeError:
                title = ""
            label = f"branch[{branch_idx}]"
            if title:
                label += f" ({title})"
            sub_path = (
                "/" + "/".join(str(p) for p in sub.absolute_path)
                if sub.absolute_path
                else "/"
            )
            lines.append(f"  - {label} at {sub_path}: {sub.message}")
    try:
        instance_preview = json.dumps(exc.instance, default=str)
    except (TypeError, ValueError):
        instance_preview = repr(exc.instance)
    if len(instance_preview) > 800:
        instance_preview = instance_preview[:800] + "...(truncated)"
    lines.append(f"instance preview: {instance_preview}")
    return "\n".join(lines)


def validate_jsonschema(output: str, schema: dict[str, Any]) -> ValidationResult:
    """Run pure JSON-Schema validation on ``output``."""
    try:
        instance = json.loads(extract_json(output))
    except json.JSONDecodeError as exc:
        return ValidationResult(
            ok=False, error=f"output is not valid JSON: {exc}", engine="jsonschema"
        )
    try:
        _jsonschema.validate(instance=instance, schema=schema)
    except _jsonschema.ValidationError as exc:
        return ValidationResult(
            ok=False, error=format_jsonschema_error(exc), engine="jsonschema"
        )
    return ValidationResult(ok=True, engine="jsonschema")


def validate_pydantic(output: str, schema: dict[str, Any]) -> ValidationResult:
    """Run Pydantic validation — catches cross-field constraints jsonschema can't."""
    from agentbox.core.prompt.composition.pydantic_validate import (
        validate_with_pydantic,
    )

    ok, err = validate_with_pydantic(output, schema)
    return ValidationResult(ok=ok, error=err, engine="pydantic")


def resolve_schema(
    agent: Any,
    workdir: Path,
    project_root: Path | None = None,
) -> tuple[dict[str, Any] | None, str]:
    """Locate the agent's output schema.

    Returns ``(schema_dict, error_msg)`` — ``schema_dict`` is ``None`` when
    no schema is configured (caller should treat the run as no-validation),
    or when the schema file is missing/unreadable (caller should surface
    ``error_msg`` as a validation failure).
    """
    from agentbox.core.agent.config import PythonAgentConfig

    composed = agent.__dict__.get("_composed_schema") if hasattr(agent, "__dict__") else None
    if isinstance(composed, dict):
        return composed, ""

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


def validate_output(
    agent: Any,
    workdir: Path,
    output: str | None,
    *,
    project_root: Path | None = None,
) -> ValidationResult:
    """Validate ``output`` against the agent's declared schema.

    Returns:
      - ``ok=True, engine="off"`` when no schema is configured.
      - ``ok=False, engine="none"`` for empty output when a schema exists.
      - The result of the configured engine otherwise
        (``jsonschema`` / ``pydantic`` / ``both``).

    Backends that produce already-typed outputs (e.g. pydantic-ai
    structured returns) may bypass this and synthesize their own result.
    """
    from agentbox.core.agent.config import ExecutionConfig

    schema, schema_err = resolve_schema(agent, workdir, project_root)
    if schema is None:
        if schema_err:
            return ValidationResult(ok=False, error=schema_err, engine="none")
        return ValidationResult(ok=True, engine="off")

    if not output:
        return ValidationResult(
            ok=False,
            error="output is empty but an output schema is required",
            engine="none",
        )

    engine = ExecutionConfig.from_agent(agent).output_validation_engine

    if engine == "jsonschema":
        return validate_jsonschema(output, schema)
    if engine == "pydantic":
        return validate_pydantic(output, schema)

    # ``both`` — jsonschema first (cheap, catches shape), then pydantic
    # (catches cross-field / type-coerced constraints).
    js = validate_jsonschema(output, schema)
    if not js.ok:
        return js
    py = validate_pydantic(output, schema)
    if not py.ok:
        return py
    return ValidationResult(ok=True, engine="both")
