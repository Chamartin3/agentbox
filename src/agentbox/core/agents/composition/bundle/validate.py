"""JSON Schema validation for composed prompts.

Behaviour controlled by ``composition.output_validation``:
- ``strict`` (default): fail the run on validation error.
- ``warn``: mark run completed with ``validation_status = "warn"``.
- ``off``: skip validation entirely.
"""

from __future__ import annotations

import json
import logging
from types import ModuleType
from typing import Any

_jsonschema: ModuleType | None
try:
    import jsonschema as _jsonschema
except ImportError:  # pragma: no cover
    _jsonschema = None

logger = logging.getLogger(__name__)


def validate_input(
    variables: dict[str, str], required: list[str] | None = None
) -> list[str]:
    """Validate that all required variables are present.

    Returns a list of missing variable names (empty if OK).
    """
    required = required or []
    missing = [k for k in required if k not in variables]
    return missing


def precompose_check(
    response: str, schema: dict[str, Any] | None, mode: str = "strict"
) -> tuple[bool, list[str]]:
    """Pre-compose validation of a runner's output against a JSON Schema.

    This is **not** the runtime ``validate_output`` entrypoint — it is a
    composition-time helper for checking bundle output before the run starts.
    Runtime validation lives in ``core.agents.contract.check``.

    Args:
        response: raw output text (expected to be JSON).
        schema: JSON Schema dict (``None`` → auto-pass).
        mode: ``strict`` | ``warn`` | ``off``.

    Returns:
        ``(ok, errors)`` where ``ok`` is ``True`` when validation passes
        or is skipped, and ``errors`` is a list of human-readable messages.
    """
    if mode == "off" or schema is None:
        return True, []

    try:
        instance = json.loads(response)
    except json.JSONDecodeError as exc:
        return False, [f"output is not valid JSON: {exc}"]

    if _jsonschema is None:
        return _basic_shape_check(instance, schema)

    validator = _jsonschema.Draft202012Validator(schema)
    errors = [str(e.message) for e in validator.iter_errors(instance)]
    return len(errors) == 0, errors


def _basic_shape_check(instance: Any, schema: dict[str, Any]) -> tuple[bool, list[str]]:
    """Fallback validation when ``jsonschema`` is not installed."""
    errors: list[str] = []
    if not isinstance(instance, dict):
        return False, ["output must be a JSON object"]

    props = schema.get("properties", {})
    required = schema.get("required", [])

    for field in required:
        if field not in instance:
            errors.append(f"missing required field: {field}")
            continue
        field_schema = props.get(field, {})
        expected_type = field_schema.get("type")
        if expected_type:
            type_map = {
                "string": str,
                "integer": int,
                "number": (int, float),
                "boolean": bool,
                "object": dict,
                "array": list,
            }
            py_type = type_map.get(expected_type)
            if py_type and not isinstance(instance[field], py_type):
                errors.append(
                    f"field {field!r}: expected {expected_type}, "
                    f"got {type(instance[field]).__name__}"
                )
        enum_vals = field_schema.get("enum")
        if enum_vals and instance[field] not in enum_vals:
            errors.append(
                f"field {field!r}: must be one of {enum_vals}, got {instance[field]!r}"
            )

    return len(errors) == 0, errors
