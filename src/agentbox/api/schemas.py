"""Shared API response shapes.

Provides the pagination envelope ``PaginatedEnvelope`` and the in-memory
sort/filter/page helper ``paginate_list`` used by list endpoints throughout
``agentbox.api``.

The wire contract is ``{items, total, offset, limit, has_more}``.  DB-level
sort can be added per-endpoint later without changing the contract.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import Any, Generic, TypedDict, TypeVar

T = TypeVar("T")


class PaginatedEnvelope(TypedDict, Generic[T]):
    items: list[T]
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
    items: Sequence[T],
    *,
    q: str | None = None,
    q_fields: Iterable[str] = (),
    sort: str | None = None,
    order: str = "asc",
    limit: int = 50,
    offset: int = 0,
    sort_key: Callable[[Any, str], Any] | None = None,
) -> PaginatedEnvelope[T]:
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

    filtered: list[T] = list(items)
    if q:
        needle = q.lower()
        filtered = [
            it
            for it in items
            if any(needle in str(_get(it, f) or "").lower() for f in q_fields)
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
