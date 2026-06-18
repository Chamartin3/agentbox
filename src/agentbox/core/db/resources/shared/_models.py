"""Value types for the shared resources subpackage."""

from __future__ import annotations

import json
from typing import Any, Mapping

from dataclasses import dataclass


@dataclass(frozen=True)
class SharedResourceRecord:
    """Frozen record for a shared resource version."""

    id: str
    version: int
    kind: str
    name: str
    sha256: str
    created_at: str
    description: str | None = None
    content: str | None = None
    config_json: str | None = None
    is_active: bool = False
    author: str | None = None
    changelog: str | None = None
    tags: tuple[str, ...] = ()


def row_to_record(
    row: Mapping[str, Any] | Any | None,
) -> SharedResourceRecord | None:
    """Convert a row dict to SharedResourceRecord."""
    if not row:
        return None
    tags_str = row.get("tags")
    tags: tuple[str, ...] = ()
    if tags_str:
        try:
            tags_list = json.loads(tags_str)
            tags = tuple(tags_list) if isinstance(tags_list, list) else ()
        except json.JSONDecodeError:
            tags = ()

    return SharedResourceRecord(
        id=row["id"],
        version=row["version"],
        kind=row["kind"],
        name=row["name"],
        description=row.get("description"),
        content=row.get("content"),
        config_json=row.get("config_json"),
        sha256=row["sha256"],
        is_active=bool(row.get("is_active", 0)),
        author=row.get("author"),
        changelog=row.get("changelog"),
        tags=tags,
        created_at=row["created_at"],
    )
