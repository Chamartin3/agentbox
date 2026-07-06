"""Generic service-layer result envelopes.

Services return TypedDicts. These two generics replace the hand-rolled
single-field ``{items: [...]}`` wrappers and the divergent pagination shapes
in ``payload_types.py`` — alias them per call site to stay concrete, e.g.
``SkillsListResult = ItemsResult[SkillListItem]``.
"""

from __future__ import annotations

from typing import TypedDict


class ItemsResult[T](TypedDict):
    """Bare list result: ``{"items": [...]}``."""

    items: list[T]


class Paged[T](TypedDict):
    """Paginated list result with the canonical field set."""

    items: list[T]
    total: int
    limit: int
    offset: int
