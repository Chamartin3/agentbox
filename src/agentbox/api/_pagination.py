"""Shared pagination helper for list endpoints.

Provides a consistent envelope `{items, total, offset, limit, has_more}`
and an in-memory sort/filter/page helper so endpoints that don't yet have
DB-level sort can still expose the same contract that `DataTable` (server
mode) and other consumers expect.

DB-level sort can be added per-endpoint later without changing the wire
contract.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, TypedDict


class PaginatedEnvelope(TypedDict):
    items: list[Any]
    total: int
    offset: int
    limit: int
    has_more: bool


def _coerce_sort_key(value: Any) -> Any:
    """Return a value suitable for `sorted()` — None becomes sentinel."""
    if value is None:
        return ""
    return value


def paginate_list(
    items: list[Any],
    *,
    q: str | None = None,
    q_fields: Iterable[str] = (),
    sort: str | None = None,
    order: str = "asc",
    limit: int = 50,
    offset: int = 0,
    sort_key: Callable[[Any, str], Any] | None = None,
) -> PaginatedEnvelope:
    """Apply search/sort/pagination to an in-memory list of dicts.

    `q` is matched case-insensitively against `q_fields` (dotted paths NOT
    supported — keep filterable fields top-level on the item).

    `sort_key` lets the caller override how a field is extracted (default
    is `item.get(field)` for dicts, `getattr(item, field, None)` otherwise).
    """
    def _get(item: Any, field: str) -> Any:
        if sort_key is not None:
            return sort_key(item, field)
        if isinstance(item, dict):
            return item.get(field)
        return getattr(item, field, None)

    filtered = items
    if q:
        needle = q.lower()
        filtered = [
            it for it in items
            if any(
                needle in str(_get(it, f) or "").lower()
                for f in q_fields
            )
        ]

    if sort:
        reverse = order.lower() == "desc"
        filtered = sorted(
            filtered,
            key=lambda it: _coerce_sort_key(_get(it, sort)),
            reverse=reverse,
        )

    total = len(filtered)
    sliced = filtered[offset : offset + limit] if limit > 0 else filtered[offset:]
    return {
        "items": sliced,
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + len(sliced) < total,
    }
