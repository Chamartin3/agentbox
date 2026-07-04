"""Validation gates — jsonschema, pydantic, HTTP callback, script."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any


import httpx
import jsonschema as _jsonschema

from agentbox.core.config import SETTINGS
from agentbox.core.agents.validation.errors import (
    extract_json,
    format_jsonschema_error,
)
from agentbox.core.agents.validation.pydantic import validate_with_pydantic
from agentbox.core.agents.validation.schema import ValidationResult


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


__all__ = [
    "call_http_validator",
    "call_script_validator",
    "run_json_schema",
    "validate_jsonschema",
    "validate_pydantic",
]
