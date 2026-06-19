"""Main ``validate_output`` entry point — orchestrates the two-gate pipeline."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from agentbox.core.agents.config import ExecutionConfig, resolve_output_config

from agentbox.core.agents.validation.gates import (
    call_http_validator,
    call_script_validator,
    run_json_schema,
    validate_jsonschema,
    validate_pydantic,
)
from agentbox.core.agents.validation.schema import (
    ValidationEngine,
    ValidationResult,
    resolve_schema,
)


def _run_gates(
    json_schema: dict[str, Any] | None,
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
        result = run_json_schema(json_schema, output)
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

    engine: ValidationEngine
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


def validate_output(
    agent: Any,
    workdir: Any,
    output: str | None,
    *,
    project_root: Any = None,
    store: Any | None = None,
    composed: Any | None = None,
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


__all__ = ["validate_output"]
