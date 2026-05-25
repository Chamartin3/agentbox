"""Loose JSON-Schema → pydantic ``BaseModel`` converter.

This is the lenient fallback used by :class:`TokenBackend` when the
strict converter in :mod:`agentbox.core.run.backends._schema_to_model`
raises :class:`UnsupportedSchema`. It only honors basic shapes
(``type``, ``$ref``, ``oneOf``/``anyOf``, ``required``, ``default``)
and intentionally drops enums, length/pattern constraints, and the like
— losing some constraint coverage is preferred to aborting a run.

Exposed at the package top-level as
``agentbox.core.run.backends.token._json_schema_to_pydantic_model`` for
backward compatibility with callers and tests that imported it from the
old single-module ``token.py``.
"""

from __future__ import annotations

from typing import Any, Union

from pydantic import create_model


def _json_schema_to_pydantic_model(
    schema: dict[str, Any],
    *,
    model_name: str = "OutputModel",
) -> Any:
    """Convert a JSON Schema dict to a pydantic ``BaseModel``.

    Handles the common shapes produced by ``model_json_schema()``:
    top-level ``$defs``, ``$ref`` resolution, ``required`` lists, and
    basic types (string, integer, number, boolean, array, object).

    Falls back to a generic ``dict`` model when the schema is too complex
    to translate automatically.
    """
    defs: dict[str, Any] = schema.get("$defs", {})

    def _resolve_ref(ref: str) -> dict[str, Any]:
        # "#/$defs/Foo" → "Foo"
        parts = ref.split("/")
        name = parts[-1]
        return defs.get(name, {})

    def _json_type_to_python(field_schema: dict[str, Any]) -> Any:
        typ = field_schema.get("type")
        if "$ref" in field_schema:
            resolved = _resolve_ref(field_schema["$ref"])
            sub = _build_model_from_schema(
                resolved, name=field_schema["$ref"].split("/")[-1]
            )
            return sub
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
                resolved = _resolve_ref(items["$ref"])
                item_model = _build_model_from_schema(
                    resolved, name=items["$ref"].split("/")[-1]
                )
                return list[item_model]
            item_type = _json_type_to_python(items)
            return list[item_type] if item_type else list
        if typ == "object":
            return dict[str, Any]
        if typ == "null":
            return type(None)
        return Any

    def _build_model_from_schema(
        schema_obj: dict[str, Any],
        *,
        name: str = "NestedModel",
    ) -> Any:
        union_branches = schema_obj.get("oneOf") or schema_obj.get("anyOf")
        if union_branches:
            branch_types: list[Any] = []
            for i, branch in enumerate(union_branches):
                if "$ref" in branch:
                    resolved = _resolve_ref(branch["$ref"])
                    branch_name = branch["$ref"].split("/")[-1]
                    branch_types.append(
                        _build_model_from_schema(resolved, name=branch_name)
                    )
                else:
                    branch_name = branch.get("title") or f"{name}Branch{i}"
                    branch_types.append(
                        _build_model_from_schema(branch, name=branch_name)
                    )
            if len(branch_types) == 1:
                return branch_types[0]
            return Union[tuple(branch_types)]  # type: ignore[return-value]  # noqa: UP007

        properties = schema_obj.get("properties", {})
        required = set(schema_obj.get("required", []))
        fields: dict[str, tuple[type, Any]] = {}
        for prop_name, prop_schema in properties.items():
            py_type = _json_type_to_python(prop_schema)
            default = ... if prop_name in required else None
            if "default" in prop_schema and prop_name not in required:
                default = prop_schema["default"]
            fields[prop_name] = (py_type, default)
        if not fields:
            return create_model(name)
        return create_model(name, **fields)

    return _build_model_from_schema(schema, name=model_name)
