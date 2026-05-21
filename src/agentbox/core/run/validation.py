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
        "/" + "/".join(str(p) for p in exc.absolute_path) if exc.absolute_path else "/"
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
    invariants to actually run, configure the agent's two-gate output
    contract (``config_json["output"]``) with an HTTP validator callback.
    """
    from agentbox.core.prompt.composition.pydantic_validate import (
        validate_with_pydantic,
    )

    ok, err = validate_with_pydantic(output, schema)
    return ValidationResult(ok=ok, error=err, engine="pydantic")


def run_json_schema(schema: dict[str, Any], output: str) -> ValidationResult:
    """Gate 1: structural JSON Schema validation (local, no network)."""
    return validate_jsonschema(output, schema)


def call_http_validator(validator_cfg: Any, output: str) -> ValidationResult:
    """Gate 2: semantic validation via HTTP callback to the consumer.

    Sends ``{"output": <raw_output>}`` and expects ``{"ok": bool, "error": str}``.
    Failure to reach the endpoint surfaces as a hard failure — we never
    silently skip validation when the callback is configured.
    """
    import hashlib
    import hmac
    import json
    import os

    import httpx

    body = json.dumps({"output": output}).encode("utf-8")

    secret = os.environ.get("AGENTBOX_WEBHOOK_SECRET", "")
    sig = (
        hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        if secret
        else ""
    )

    headers = {"Content-Type": "application/json"}
    if sig:
        headers["X-Agentbox-Signature"] = sig

    try:
        resp = httpx.post(
            validator_cfg.endpoint,
            content=body,
            headers=headers,
            timeout=validator_cfg.timeout_seconds,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.TimeoutException:
        return ValidationResult(
            ok=False,
            error=f"callback unreachable: timed out after {validator_cfg.timeout_seconds}s",
            engine="http-callback",
        )
    except httpx.HTTPStatusError as exc:
        return ValidationResult(
            ok=False,
            error=f"callback returned HTTP {exc.response.status_code}",
            engine="http-callback",
        )
    except Exception as exc:
        return ValidationResult(
            ok=False,
            error=f"callback unreachable: {exc}",
            engine="http-callback",
        )

    if data.get("ok"):
        return ValidationResult(ok=True, engine="http-callback")
    return ValidationResult(
        ok=False,
        error=data.get("error") or "validation failed (no error detail)",
        engine="http-callback",
    )


def call_script_validator(validator_cfg: Any, output: str) -> ValidationResult:
    """Run a Python script validator in-process.

    Convention: the script must define a top-level callable::

        def validate(output: str) -> dict:  # {"ok": bool, "error": str}

    Security note: the script runs in this process with full privileges.
    Operators upload it as a versioned ``script`` resource, so trust is
    the same as the agent's own prompt and tool grants. A subprocess /
    sandbox boundary can be layered in later without changing the
    contract above.
    """
    src = (validator_cfg.source_code or "").strip()
    if not src:
        return ValidationResult(
            ok=False,
            error=(
                f"script validator for resource {validator_cfg.resource_id!r} "
                "has no source — the resource version may have no blob"
            ),
            engine="script",
        )
    namespace: dict[str, Any] = {"__name__": "agentbox_script_validator"}
    try:
        exec(compile(src, "<script_validator>", "exec"), namespace)
    except Exception as exc:
        return ValidationResult(
            ok=False,
            error=f"script validator failed to load: {exc}",
            engine="script",
        )
    fn = namespace.get("validate")
    if not callable(fn):
        return ValidationResult(
            ok=False,
            error="script validator must define a top-level `validate(output: str)` function",
            engine="script",
        )
    try:
        result = fn(output)
    except Exception as exc:
        return ValidationResult(
            ok=False,
            error=f"script validator raised: {exc}",
            engine="script",
        )
    if not isinstance(result, dict):
        return ValidationResult(
            ok=False,
            error=(
                "script validator returned "
                f"{type(result).__name__!s}; expected a dict {{ok, error}}"
            ),
            engine="script",
        )
    if result.get("ok"):
        return ValidationResult(ok=True, engine="script")
    return ValidationResult(
        ok=False,
        error=str(result.get("error") or "script validator returned ok=False"),
        engine="script",
    )


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
      2. ``python.output_schema_path`` (legacy file-based contract).
    """
    from agentbox.core.agent.config import PythonAgentConfig

    composed = (
        agent.__dict__.get("_composed_schema") if hasattr(agent, "__dict__") else None
    )
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
    store: Any | None = None,
) -> ValidationResult:
    """Validate ``output`` against the agent's declared schema.

    Two-gate architecture:
      Gate 1 (structural): JSON Schema from the agent's ``output_schema``
        resource binding. Catches malformed JSON, missing required fields,
        wrong types, per-field min/max constraints.
      Gate 2..N (semantic): explicit validators (``http``, ``script``, …)
        listed in the agent version's bound validation contract. Run only
        when that contract carries entries.

    ``store`` is needed to resolve the output binding + bound contract.
    When omitted, the function falls back to the legacy on-disk schema
    path (``runner.output_schema_path``). New code must pass ``store``.

    Returns:
      - ``ok=True, engine="off"`` when no schema is configured.
      - ``ok=False, engine="none"`` for empty output when a schema exists.
    """
    from agentbox.core.agent.config import ExecutionConfig, resolve_output_config

    # --- Validation: schema (implicit) + contract validators (explicit) ---
    output_cfg = resolve_output_config(store, agent)
    if output_cfg.json_schema is not None or output_cfg.validators:
        if not output:
            return ValidationResult(
                ok=False,
                error="output is empty but an output schema is required",
                engine="none",
            )
        # Gate 1: implicit jsonschema validator (from the agent's
        # output_schema binding). Skipped only when no schema exists.
        if output_cfg.json_schema is not None:
            result = run_json_schema(output_cfg.json_schema, output)
            if not result.ok:
                return result
        # Gate 2..N: explicit validators from the bound contract.
        # Dispatch by kind. Adding a new kind here is the only runtime
        # change required to support it end-to-end.
        ran_http = False
        ran_script = False
        for vcfg in output_cfg.validators:
            if vcfg.kind == "http":
                result = call_http_validator(vcfg, output)
                if not result.ok:
                    return result
                ran_http = True
            elif vcfg.kind == "script":
                result = call_script_validator(vcfg, output)
                if not result.ok:
                    return result
                ran_script = True
            else:
                return ValidationResult(
                    ok=False,
                    error=f"unknown validator kind: {vcfg.kind}",
                    engine="none",
                )
        # Compose engine label so the recorded run reflects which gates fired.
        engine: ValidationEngine
        if output_cfg.json_schema is not None and ran_http:
            engine = "json-schema+http-callback"
        elif output_cfg.json_schema is not None and ran_script:
            engine = "json-schema+script"
        elif ran_http:
            engine = "http-callback"
        elif ran_script:
            engine = "script"
        elif output_cfg.json_schema is not None:
            engine = "json-schema"
        else:
            engine = "off"
        return ValidationResult(ok=True, engine=engine)

    # --- Legacy path: schema file ---
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

    engine_name = ExecutionConfig.from_agent(agent).output_validation_engine

    if engine_name == "jsonschema":
        return validate_jsonschema(output, schema)
    if engine_name == "pydantic":
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
