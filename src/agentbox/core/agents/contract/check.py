"""Output validation — schema gates, error formatting, and orchestration.

Merged from ``validation/{gates,orchestrate,pydantic,errors}.py``.
Renames public verb ``validate_output`` → ``check_output``.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import hashlib
import hmac
import json
import jsonschema as _jsonschema

from agentbox.core.agents.contract.schema import (
    resolve_output_config,
    resolve_schema,
)
from agentbox.core.agents.definition import ExecutionConfig
from agentbox.core.config import SETTINGS
from agentbox.core.data.composition import ValidationResult
from agentbox.core.data.payload_types import JsonSchemaDict
from agentbox.core.data._util import extract_json
from agentbox.core.engines.contracts.schema_to_model.translate import (
    json_schema_to_pydantic_model,
)

import httpx


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
    try:
        instance = json.loads(extract_json(output))
    except json.JSONDecodeError as exc:
        return ValidationResult(
            ok=False, error=f"output is not valid JSON: {exc}", engine="pydantic"
        )

    try:
        model = json_schema_to_pydantic_model(schema, model_name="OutputModel")
    except Exception as exc:
        return ValidationResult(
            ok=False,
            error=f"cannot build pydantic model from schema: {exc}",
            engine="pydantic",
        )

    try:
        model.model_validate(instance)
        return ValidationResult(ok=True, engine="pydantic")
    except Exception as exc:
        return ValidationResult(ok=False, error=str(exc), engine="pydantic")


def run_json_schema(schema: dict[str, Any], output: str) -> ValidationResult:
    """Gate 1: structural JSON Schema validation (local, no network)."""
    return validate_jsonschema(output, schema)


def call_http_validator(validator_cfg: Any, output: str) -> ValidationResult:
    """Gate 2: semantic validation via HTTP callback to the consumer.

    Sends ``{"output": <raw_output>}`` and expects ``{"ok": bool, "error": str}``.
    Failure to reach the endpoint surfaces as a hard failure — we never
    silently skip validation when the callback is configured.
    """
    body = json.dumps({"output": output}).encode("utf-8")

    secret = SETTINGS.webhook_secret
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
    namespace = {"__name__": "agentbox_script_validator"}
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


def _run_gates(
    json_schema: JsonSchemaDict | None,
    validators: Iterable[Any],
    output: str,
) -> ValidationResult:
    """Execute the two-gate validation sequence.

    Gate 1 (structural): JSON Schema validation.
    Gate 2..N (semantic): explicit http/script validators.

    This helper exists in exactly one place so both the agent-based and
    view-based entrypoints run identical gate logic.
    """
    if json_schema is not None:
        result = run_json_schema(dict(json_schema), output)
        if not result.ok:
            return result

    ran_http = False
    ran_script = False
    for vcfg in validators:
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

    engine: str
    if json_schema is not None and ran_http:
        engine = "json-schema+http-callback"
    elif json_schema is not None and ran_script:
        engine = "json-schema+script"
    elif ran_http:
        engine = "http-callback"
    elif ran_script:
        engine = "script"
    elif json_schema is not None:
        engine = "json-schema"
    else:
        engine = "off"
    return ValidationResult(ok=True, engine=engine)


def check_output(
    agent: Any,
    workdir: Any,
    output: str | None,
    *,
    project_root: Any = None,
    store: Any | None = None,
    composed: Any | None = None,
) -> ValidationResult:
    """Check ``output`` against the agent's declared schema.

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
    output_cfg = resolve_output_config(store, agent)
    if output_cfg.json_schema is not None or output_cfg.validators:
        if not output:
            return ValidationResult(
                ok=False,
                error="output is empty but an output schema is required",
                engine="none",
            )
        return _run_gates(output_cfg.json_schema, output_cfg.validators, output)

    composed_schema = getattr(composed, "schema", None) if composed is not None else None
    schema, schema_err = resolve_schema(
        agent, workdir, project_root, composed_schema=composed_schema
    )
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

    js = validate_jsonschema(output, schema)
    if not js.ok:
        return js
    py = validate_pydantic(output, schema)
    if not py.ok:
        return py
    return ValidationResult(ok=True, engine="both")


__all__ = [
    "call_http_validator",
    "call_script_validator",
    "check_output",
    "format_jsonschema_error",
    "run_json_schema",
    "validate_jsonschema",
    "validate_pydantic",
]
