"""Pydantic-backed output validation from JSON Schema.

Builds a dynamic pydantic ``BaseModel`` from the JSON Schema dict, then
validates the parsed output through it.  This catches issues that
``jsonschema`` may miss — type coercion, string constraints, and
required-field enforcement with pydantic-style error messages.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, create_model


def _extract_json(text: str) -> str:
    """Strip markdown code fences if present."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return stripped


def _json_type_to_python(
    field_schema: dict[str, Any],
    defs: dict[str, Any],
    depth: int = 0,
) -> Any:
    """Map a JSON Schema type fragment to a Python type."""
    if depth > 10:
        return Any

    if "$ref" in field_schema:
        ref_name = field_schema["$ref"].split("/")[-1]
        resolved = defs.get(ref_name, {})
        return _build_model_from_schema(
            resolved, name=ref_name, defs=defs, depth=depth + 1
        )

    typ = field_schema.get("type")
    if typ == "string":
        return str
    if typ == "integer":
        return int
    if typ == "number":
        return float
    if typ == "boolean":
        return bool
    if typ == "array":
        items = field_schema.get("items", {})
        if "$ref" in items:
            ref_name = items["$ref"].split("/")[-1]
            resolved = defs.get(ref_name, {})
            item_model = _build_model_from_schema(
                resolved, name=ref_name, defs=defs, depth=depth + 1
            )
            return list[item_model]
        item_type = _json_type_to_python(items, defs, depth + 1)
        return list[item_type] if item_type else list
    if typ == "object":
        return dict[str, Any]
    if typ == "null":
        return type(None)
    return Any


def _empty_model(name: str) -> type[BaseModel]:
    """Return a concrete empty model — never bare ``BaseModel``.

    ``BaseModel`` itself can't be instantiated in pydantic v2, so empty
    schemas must produce a real subclass.
    """
    return create_model(name)


def _build_model_from_schema(
    schema_obj: dict[str, Any],
    *,
    name: str = "NestedModel",
    defs: dict[str, Any] | None = None,
    depth: int = 0,
) -> type[BaseModel]:
    """Build a pydantic ``BaseModel`` from a JSON Schema object dict."""
    if depth > 10:
        return _empty_model(name)

    all_defs = defs or schema_obj.get("$defs", {})
    properties = schema_obj.get("properties", {})
    required = set(schema_obj.get("required", []))
    fields: dict[str, tuple[type, Any]] = {}
    for prop_name, prop_schema in properties.items():
        py_type = _json_type_to_python(prop_schema, all_defs, depth + 1)
        default = ... if prop_name in required else None
        if "default" in prop_schema and prop_name not in required:
            default = prop_schema["default"]
        fields[prop_name] = (py_type, default)
    if not fields:
        return _empty_model(name)
    return create_model(name, **fields)


def validate_with_pydantic(
    output_text: str,
    schema: dict[str, Any],
) -> tuple[bool, str]:
    """Validate *output_text* against *schema* using a dynamic pydantic model.

    Returns ``(True, "")`` on success or ``(False, error_message)`` on
    failure.  The error message is a concise pydantic-style string.
    """
    try:
        instance = json.loads(_extract_json(output_text))
    except json.JSONDecodeError as exc:
        return False, f"output is not valid JSON: {exc}"

    try:
        model = _build_model_from_schema(schema, name="OutputModel")
    except Exception as exc:
        return False, f"cannot build pydantic model from schema: {exc}"

    try:
        model.model_validate(instance)
        return True, ""
    except Exception as exc:
        return False, str(exc)
