"""JSON Schema → Pydantic model converter (runtime).

Isolated helper for the ``token`` backend so pydantic-ai can enforce
the full validation contract.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Literal, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, RootModel, create_model

from agentbox.core.engines.contracts.schema_to_model.consistency import (
    UnsupportedSchema,
    assert_schema_consistent,
)

_FORMAT_TYPES: dict[str, Any] = {
    "date": date,
    "date-time": datetime,
    "datetime": datetime,
    "uuid": UUID,
}


def json_schema_to_pydantic_model(
    schema: dict[str, Any],
    *,
    model_name: str = "AgentOutput",
) -> type[BaseModel]:
    """Convert a JSON Schema document into a pydantic ``BaseModel``.

    The returned model preserves: required fields, enums, string
    ``minLength``/``maxLength``/``pattern``/``format``, numeric
    ``minimum``/``maximum``/``exclusive*``/``multipleOf``, array
    ``minItems``/``maxItems``, ``additionalProperties=false`` →
    ``extra='forbid'``, ``description`` and ``default``.

    Raises :class:`UnsupportedSchema` if the schema references a
    construct not handled here (so the caller can choose to fall back).
    """
    assert_schema_consistent(schema)

    cache: dict[str, type[BaseModel]] = {}

    def resolve_ref(ref: str) -> dict[str, Any]:
        if not ref.startswith("#/"):
            raise UnsupportedSchema(f"external $ref not supported: {ref!r}")
        parts = ref.lstrip("#/").split("/")
        node: Any = schema
        for p in parts:
            if not isinstance(node, dict) or p not in node:
                raise UnsupportedSchema(f"$ref target missing: {ref!r}")
            node = node[p]
        return node

    def type_for(field_schema: dict[str, Any], *, name_hint: str) -> Any:
        if "$ref" in field_schema:
            target_name = field_schema["$ref"].rsplit("/", 1)[-1]
            if target_name in cache:
                return cache[target_name]
            resolved = resolve_ref(field_schema["$ref"])
            sub = build_object(resolved, name=target_name)
            return sub

        for key in ("anyOf", "oneOf"):
            if key in field_schema:
                branches = field_schema[key]
                branch_types: list[type[Any]] = []
                for i, branch in enumerate(branches):
                    t = type_for(branch, name_hint=f"{name_hint}{key.title()}{i}")
                    branch_types.append(t)
                if len(branch_types) == 1:
                    return branch_types[0]
                return Union[tuple(branch_types)]  # noqa: UP007

        if "const" in field_schema:
            return Literal[field_schema["const"]]

        if "enum" in field_schema:
            values = tuple(field_schema["enum"])
            return Literal[values]

        typ = field_schema.get("type")
        if isinstance(typ, list):
            non_null = [t for t in typ if t != "null"]
            if len(non_null) == 1 and "null" in typ:
                inner = type_for(
                    {**field_schema, "type": non_null[0]}, name_hint=name_hint
                )
                return inner | None
            raise UnsupportedSchema(f"union type {typ!r} not supported")

        if typ == "string":
            fmt = field_schema.get("format")
            if fmt and fmt in _FORMAT_TYPES:
                return _FORMAT_TYPES[fmt]
            return str
        if typ == "integer":
            return int
        if typ == "number":
            return float
        if typ == "boolean":
            return bool
        if typ == "null":
            return type(None)
        if typ == "array":
            items = field_schema.get("items")
            if items is None:
                return list
            inner = type_for(items, name_hint=f"{name_hint}Item")
            return list[inner]
        if typ == "object":
            if "properties" in field_schema or "required" in field_schema:
                return build_object(field_schema, name=name_hint)
            return dict[str, Any]
        if typ is None:
            return Any
        raise UnsupportedSchema(f"unknown type {typ!r}")

    def field_for(prop_schema: dict[str, Any], *, required: bool) -> Any:
        kwargs: dict[str, Any] = {}
        if "description" in prop_schema:
            kwargs["description"] = prop_schema["description"]
        if "title" in prop_schema:
            kwargs["title"] = prop_schema["title"]
        if "minLength" in prop_schema:
            kwargs["min_length"] = prop_schema["minLength"]
        if "maxLength" in prop_schema:
            kwargs["max_length"] = prop_schema["maxLength"]
        if "pattern" in prop_schema:
            pat = prop_schema["pattern"]
            try:
                re.compile(pat)
                kwargs["pattern"] = pat
            except re.error as exc:
                raise UnsupportedSchema(f"invalid regex {pat!r}: {exc}") from exc
        if "minimum" in prop_schema:
            kwargs["ge"] = prop_schema["minimum"]
        if "maximum" in prop_schema:
            kwargs["le"] = prop_schema["maximum"]
        if "exclusiveMinimum" in prop_schema:
            kwargs["gt"] = prop_schema["exclusiveMinimum"]
        if "exclusiveMaximum" in prop_schema:
            kwargs["lt"] = prop_schema["exclusiveMaximum"]
        if "multipleOf" in prop_schema:
            kwargs["multiple_of"] = prop_schema["multipleOf"]
        if "minItems" in prop_schema:
            kwargs["min_length"] = prop_schema["minItems"]
        if "maxItems" in prop_schema:
            kwargs["max_length"] = prop_schema["maxItems"]
        if required:
            if "default" in prop_schema:
                kwargs["default"] = prop_schema["default"]
                return Field(**kwargs)
            return Field(..., **kwargs) if kwargs else ...
        kwargs["default"] = prop_schema.get("default")
        return Field(**kwargs)

    def build_object(obj_schema: dict[str, Any], *, name: str) -> type[BaseModel]:
        if name in cache:
            return cache[name]

        properties: dict[str, Any] = obj_schema.get("properties", {}) or {}
        required = set(obj_schema.get("required", []) or [])
        additional_properties = obj_schema.get("additionalProperties", True)

        if name in cache:
            return cache[name]

        fields: dict[str, tuple[Any, Any]] = {}
        for prop_name, prop_schema in properties.items():
            is_required = prop_name in required
            py_type = type_for(prop_schema, name_hint=_capitalize(prop_name))
            if not is_required:
                py_type = py_type | None
            field_default = field_for(prop_schema, required=is_required)
            fields[prop_name] = (py_type, field_default)

        config = (
            ConfigDict(extra="forbid")
            if additional_properties is False
            else ConfigDict()
        )
        create_model_any: Any = create_model
        if fields:
            model = create_model_any(name, __config__=config, **fields)
        else:
            model = create_model_any(name, __config__=config)

        cache[name] = model
        return model

    for union_key in ("oneOf", "anyOf"):
        if union_key in schema:
            wrapper = type_for(
                {union_key: schema[union_key]},
                name_hint=model_name,
            )
            root_cls: type[BaseModel] = RootModel[wrapper]
            root_cls.__name__ = model_name
            return root_cls

    root_type = schema.get("type", "object")
    if root_type != "object":
        raise UnsupportedSchema(f"root schema type must be object, got {root_type!r}")
    return build_object(schema, name=model_name)


def _capitalize(s: str) -> str:
    return (
        "".join(p[:1].upper() + p[1:] for p in s.replace("-", "_").split("_") if p)
        or "Field"
    )


__all__ = ["json_schema_to_pydantic_model"]
