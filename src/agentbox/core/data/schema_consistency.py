"""Schema consistency checker — ensures ``required`` ⊆ ``properties`` everywhere.

A pure, stdlib-only walker over a JSON Schema dict. It lives at the
shapes leaf because both domains need it: the agents domain runs it as
the agent output-contract gate (at the executor boundary), and the
engines token backend's ``json_schema_to_pydantic_model`` calls it before
building a pydantic model. Since ``engines`` must never import
``agents``, the shared check lives here in ``core.data``.
"""

from __future__ import annotations

from typing import Any

from agentbox.core.data.errors.schemas import InconsistentSchema


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

        add = node.get("additionalProperties")
        if isinstance(add, dict):
            _walk(add, f"{where}.additionalProperties")

    _walk(schema, path)


__all__ = ["assert_schema_consistent"]
