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

import importlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import jsonschema as _jsonschema
from pydantic import BaseModel, ValidationError

# Engine label for the validator that produced the verdict. ``off`` means
# no schema is configured and validation was skipped; ``none`` means a
# schema was expected but the input was unrunnable (empty / unparseable).
# ``pydantic-class`` means we validated against the canonical Pydantic
# class declared by ``output_model`` — the only engine that runs
# ``@model_validator`` rules (cross-field invariants that JSON Schema
# cannot express).
ValidationEngine = Literal[
    "jsonschema", "pydantic", "pydantic-class", "both", "none", "off"
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
    """Run Pydantic validation — catches cross-field constraints jsonschema can't.

    NOTE: this builds a *throwaway* pydantic model from the JSON Schema
    dict, which drops ``@model_validator`` rules and most ``Field(...)``
    constraints (they don't exist in JSON Schema). For cross-field
    invariants to actually run, the agent must declare ``output_model``
    and the executor will dispatch to :func:`validate_pydantic_class`
    instead.
    """
    from agentbox.core.prompt.composition.pydantic_validate import (
        validate_with_pydantic,
    )

    ok, err = validate_with_pydantic(output, schema)
    return ValidationResult(ok=ok, error=err, engine="pydantic")


def load_output_model(dotted: str) -> type[BaseModel]:
    """Import a Pydantic class from a ``"module.path:ClassName"`` string.

    Raises :class:`ImportError` / :class:`AttributeError` / :class:`TypeError`
    on misconfiguration so the executor can surface a clear validation
    error rather than silently falling back to a weaker engine.
    """
    if ":" not in dotted:
        raise ValueError(
            f"output_model must be 'module.path:ClassName', got {dotted!r}"
        )
    module_path, cls_name = dotted.split(":", 1)
    module = importlib.import_module(module_path)
    cls = getattr(module, cls_name, None)
    if cls is None:
        raise ImportError(f"{cls_name!r} not found in {module_path}")
    if not (isinstance(cls, type) and issubclass(cls, BaseModel)):
        raise TypeError(
            f"output_model {dotted!r} must point at a pydantic.BaseModel subclass"
        )
    return cls


def validate_pydantic_class(
    output: str, model_cls: type[BaseModel]
) -> ValidationResult:
    """Validate ``output`` against the *canonical* Pydantic class.

    This is the only engine that runs ``@model_validator`` rules and
    full ``Field(...)`` constraints. Both Django and agentbox call into
    the same class, so a payload accepted here is accepted there.
    """
    try:
        payload = extract_json(output)
    except Exception as exc:  # defensive — extract_json is forgiving
        return ValidationResult(
            ok=False, error=f"could not extract JSON: {exc}", engine="pydantic-class"
        )
    try:
        instance = json.loads(payload)
    except json.JSONDecodeError as exc:
        return ValidationResult(
            ok=False, error=f"output is not valid JSON: {exc}", engine="pydantic-class"
        )
    try:
        model_cls.model_validate(instance)
    except ValidationError as exc:
        return ValidationResult(
            ok=False, error=str(exc), engine="pydantic-class"
        )
    return ValidationResult(ok=True, engine="pydantic-class")


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

    Resolution order:
      1. ``agent._composed_schema`` (already-rendered binding).
      2. ``python.output_model`` (dotted Pydantic class) — derives the
         schema via ``model_json_schema()`` so the prompt and the
         validator share a single source of truth.
      3. ``python.output_schema_path`` (legacy file-based contract).
    """
    from agentbox.core.agent.config import PythonAgentConfig

    composed = agent.__dict__.get("_composed_schema") if hasattr(agent, "__dict__") else None
    if isinstance(composed, dict):
        return composed, ""

    python_cfg = PythonAgentConfig.from_agent(agent)
    if python_cfg.output_model:
        try:
            cls = load_output_model(python_cfg.output_model)
        except (ImportError, AttributeError, TypeError, ValueError) as exc:
            return None, f"cannot load output_model {python_cfg.output_model!r}: {exc}"
        try:
            return cls.model_json_schema(), ""
        except Exception as exc:  # pydantic emits various errors here
            return None, f"cannot derive JSON schema from {python_cfg.output_model!r}: {exc}"

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

    When ``python.output_model`` is configured we short-circuit to
    :func:`validate_pydantic_class` regardless of
    ``output_validation_engine`` — the canonical class is the only
    engine that runs cross-field invariants, so honoring the legacy
    ``jsonschema`` / ``pydantic`` knobs would silently weaken the check.
    """
    from agentbox.core.agent.config import ExecutionConfig, PythonAgentConfig

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

    output_model_path = PythonAgentConfig.from_agent(agent).output_model
    if output_model_path:
        try:
            model_cls = load_output_model(output_model_path)
        except (ImportError, AttributeError, TypeError, ValueError) as exc:
            return ValidationResult(
                ok=False,
                error=f"cannot load output_model {output_model_path!r}: {exc}",
                engine="none",
            )
        return validate_pydantic_class(output, model_cls)

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
