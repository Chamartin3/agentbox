"""Canonical recursive JSON type aliases — the leaf-pure home for the
``JsonValue`` / ``JsonDict`` vocabulary.

These are the sanctioned concrete alternative to the banned
``dict[str, Any]`` / ``dict[str, object]`` for *genuinely open* JSON:
user config passthroughs, provider payloads, ``config_json`` blobs, and
JSON Schema documents. They are NOT ``Any`` — they are a closed recursive
union of everything ``json.loads`` / ``json.dumps`` can produce.

Stdlib-only, so ``core.data`` stays the dependency-graph leaf.
"""

from __future__ import annotations

type JsonValue = str | int | float | bool | None | dict[str, JsonValue] | list[JsonValue]
"""Any JSON-serializable value."""

type JsonDict = dict[str, JsonValue]
"""A JSON object — the common ``dict[str, JsonValue]`` case."""
