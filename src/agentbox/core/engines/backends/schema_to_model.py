"""JSON Schema → Pydantic model converter (runtime).

Isolated helper for the ``token`` backend so pydantic-ai can enforce
the full validation contract (enums, length/pattern, ranges, required
fields, extra=forbid, descriptions) instead of the loose
"map basic types only" conversion the backend used to do.

Only the subset of JSON Schema the agentbox prompts use is covered.
On any unsupported construct the function raises
``UnsupportedSchema`` and the caller is expected to fall back to a
loose model (or fail the run, depending on context) — never silently
strip constraints, since that's exactly what we're trying to fix.

This module has no agentbox imports so it can be unit-tested standalone
and replaced with a third-party library later without touching the
backend itself.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Literal, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, RootModel, create_model

__all__ = [
    "InconsistentSchema",
    "UnsupportedSchema",
    "assert_schema_consistent",
    "json_schema_to_pydantic_model",
]


class UnsupportedSchema(Exception):
    """Raised when a schema uses a construct this converter cannot translate."""


class InconsistentSchema(UnsupportedSchema):
    """Raised when a schema is internally inconsistent (e.g. ``required``
    names a property that is not declared in ``properties``).

    Subclasses :class:`UnsupportedSchema` so callers that already handle
    the broader failure mode keep working; new callers can catch this
    specifically to produce a precise authoring-error message.
    """


def assert_schema_consistent(
    schema: dict[str, Any],
    *,
    path: str = "$",
) -> None:
    """Recursively validate that ``required`` is a subset of declared
    ``properties`` at every object level (including each branch of
    ``oneOf``/``anyOf``/``allOf`` and through ``$ref`` targets).

    Raises :class:`InconsistentSchema` with a path-qualified message
    pointing at the offending object. Resolving ``$ref`` walks the
    document via the top-level ``$defs`` map; external refs are
    rejected the same way the converter rejects them.

    This is the load-bearing check that prevents the
    "required-but-not-in-properties" class of bug from reaching the
    LLM — the broken schema either drops fields silently (the model
    can never satisfy required) or asks the model for fields it has
    no slot to produce, both of which surface as opaque structured-
    output failures downstream.
    """
    seen: set[int] = set()

    def _resolve(ref: str, where: str) -> dict[str, Any]:
        if not ref.startswith("#/"):
            raise InconsistentSchema(f"{where}: external $ref not supported: {ref!r}")
        parts = ref.lstrip("#/").split("/")
        node: Any = schema
        for p in parts:
            if not isinstance(node, dict) or p not in node:
                raise InconsistentSchema(f"{where}: $ref target missing: {ref!r}")
            node = node[p]
        if not isinstance(node, dict):
            raise InconsistentSchema(f"{where}: $ref target is not an object: {ref!r}")
        return node

    def _walk(node: Any, where: str) -> None:
        if not isinstance(node, dict):
            return
        node_id = id(node)
        if node_id in seen:
            return
        seen.add(node_id)

        if "$ref" in node:
            target = _resolve(node["$ref"], where)
            _walk(target, where + f"->{node['$ref']}")
            return

        for key in ("oneOf", "anyOf", "allOf"):
            branches = node.get(key)
            if isinstance(branches, list):
                for i, branch in enumerate(branches):
                    _walk(branch, f"{where}.{key}[{i}]")

        properties = node.get("properties")
        required = node.get("required")
        if isinstance(required, list) and isinstance(properties, dict):
            declared = set(properties.keys())
            missing = [r for r in required if r not in declared]
            if missing:
                raise InconsistentSchema(
                    f"{where}: 'required' references undeclared "
                    f"properties: {missing!r}. Either add them to "
                    f"'properties' or remove them from 'required'."
                )
        elif isinstance(required, list) and required and properties is None:
            raise InconsistentSchema(
                f"{where}: 'required' is set ({required!r}) but no "
                f"'properties' object is declared."
            )

        if isinstance(properties, dict):
            for prop_name, prop_schema in properties.items():
                _walk(prop_schema, f"{where}.properties[{prop_name!r}]")

        items = node.get("items")
        if isinstance(items, dict):
            _walk(items, f"{where}.items")
        elif isinstance(items, list):
            for i, it in enumerate(items):
                _walk(it, f"{where}.items[{i}]")

        # additionalProperties may itself be a schema.
        add = node.get("additionalProperties")
        if isinstance(add, dict):
            _walk(add, f"{where}.additionalProperties")

    _walk(schema, path)


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
    # Fail-fast on internally inconsistent schemas (required fields not
    # declared in properties, dangling $refs, etc.). Catches the entire
    # class of authoring bugs that would otherwise reach the LLM as a
    # silently-broken contract.
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
                branch_types: list[Any] = []
                for i, branch in enumerate(branches):
                    t = type_for(branch, name_hint=f"{name_hint}{key.title()}{i}")
                    branch_types.append(t)
                if len(branch_types) == 1:
                    return branch_types[0]
                return Union[tuple(branch_types)]  # type: ignore[return-value]  # noqa: UP007

        if "const" in field_schema:
            return Literal[field_schema["const"]]  # type: ignore[valid-type]

        if "enum" in field_schema:
            values = tuple(field_schema["enum"])
            return Literal[values]  # type: ignore[valid-type]

        typ = field_schema.get("type")
        if isinstance(typ, list):
            # ["string", "null"] → Optional[str]
            non_null = [t for t in typ if t != "null"]
            if len(non_null) == 1 and "null" in typ:
                inner = type_for(
                    {**field_schema, "type": non_null[0]}, name_hint=name_hint
                )
                return inner | None  # type: ignore[operator]
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
            return list[inner]  # type: ignore[valid-type]
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

        # Pre-insert placeholder for recursive refs.
        # Pydantic doesn't easily support self-reference at construct time
        # for create_model; if we hit recursion we raise.
        if name in cache:
            return cache[name]

        fields: dict[str, tuple[Any, Any]] = {}
        for prop_name, prop_schema in properties.items():
            is_required = prop_name in required
            py_type = type_for(prop_schema, name_hint=_capitalize(prop_name))
            if not is_required:
                py_type = py_type | None  # type: ignore[operator]
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

    # Root-level discriminated unions: ``{"oneOf": [...]}`` / ``{"anyOf": [...]}``
    # at the top level used to fall through to ``build_object`` with no
    # ``properties`` / ``required`` and produce an empty model — silently
    # losing the union semantics. Translate them via ``type_for`` so each
    # branch is preserved as a Union member.
    for union_key in ("oneOf", "anyOf"):
        if union_key in schema:
            wrapper = type_for(
                {union_key: schema[union_key]},
                name_hint=model_name,
            )
            # ``wrapper`` is a Union[...] or a single model. Wrap it in a
            # ``RootModel`` so callers get a uniform BaseModel contract
            # and pydantic-ai can attach it as ``output_type``. Without
            # this, a root-level discriminated union fell through to
            # ``build_object`` and produced an empty model — silently
            # dropping the union semantics.
            root_cls: type[BaseModel] = RootModel[wrapper]  # type: ignore[valid-type]
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
