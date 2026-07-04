"""RunRecord and SharedResourceRecord dataclasses and DB row mappers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass
class RunRecord:
    id: str
    agent_id: str
    session_id: str | None
    status: str
    input: str
    output: str | None
    error: str | None
    workdir: str | None
    transcript_path: str | None
    created_at: str
    finished_at: str | None
    config_digest: str | None = None
    agent_version_id: int | None = None
    composition_snapshot: str | None = None
    rendered_prompt: str | None = None
    variables: str | None = None
    validation_status: str | None = None
    validation_errors: str | None = None
    schema_validated_via: str | None = None
    post_status: str | None = None
    post_errors: str | None = None
    conversation_format: str | None = None
    conversation_uri: str | None = None
    runner_profile_id: str | None = None
    resource_snapshot: str | None = None
    mcp_snapshot: str | None = None
    runner_snapshot: str | None = None


@dataclass(frozen=True)
class SharedResourceRecord:
    """Frozen record for a shared resource version.

    Pure data shape — no persistence dependencies.  Relocated from
    ``core.db.resources.shared._models`` to ``core.data`` so that
    ``core.service`` and ``api`` layers can import it without pulling in
    the full ``core.db`` package (plan 109 Phase A).
    """

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


__all__ = ["RunRecord", "SharedResourceRecord", "row_to_shared_resource"]


def row_to_shared_resource(
    row: Mapping[str, Any] | Any | None,
) -> SharedResourceRecord | None:
    """Convert a DB row mapping to :class:`SharedResourceRecord`."""
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



