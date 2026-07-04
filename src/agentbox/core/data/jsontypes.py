"""Recursive JSON value aliases — the typed shape for genuinely open JSON.

Use these instead of ``dict[str, Any]`` / ``Any`` for user-config
passthrough, provider payloads, and ``*_json`` blob columns
(``python-type-safety.md`` §2: a closed recursive union is not ``Any``).
``cli/shared/constants.py`` keeps its own alias for the render layer;
core code imports from here.
"""

from __future__ import annotations

__all__ = ["JsonDict", "JsonValue"]

type JsonValue = str | int | float | bool | None | dict[str, JsonValue] | list[JsonValue]
type JsonDict = dict[str, JsonValue]
