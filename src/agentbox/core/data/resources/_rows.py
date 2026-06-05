"""Row-conversion helpers for the Resources data layer.

Public-domain helpers — shared between ``crud``, ``shared``, and ``bindings``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable

from agentbox.core.data.resources.models import (
    Resource,
    ResourceBlob,
    ResourceVersion,
)

_MIN_CHANGELOG = 3


def compute_sha256(content: str | None, config_json: str | None) -> str:
    """Derive a content hash from legacy shared_resource fields."""
    h = hashlib.sha256()
    for v in (content, config_json):
        if v is not None:
            h.update(v.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_blobs(blobs: Iterable[tuple[str, bytes]]) -> str:
    """Deterministic hash over a (relative_path, content) sequence."""
    h = hashlib.sha256()
    for rel_path, content in sorted(blobs, key=lambda b: b[0]):
        h.update(rel_path.encode("utf-8"))
        h.update(b"\x00")
        h.update(hashlib.sha256(content).digest())
        h.update(b"\x00")
    return h.hexdigest()


def validate_changelog(changelog: str) -> str:
    if not changelog or len(changelog.strip()) < _MIN_CHANGELOG:
        raise ValueError(
            f"changelog/reason must be at least {_MIN_CHANGELOG} characters"
        )
    return changelog.strip()


def tags_to_db(tags: Iterable[str] | None) -> str | None:
    if not tags:
        return None
    return ",".join(t.strip() for t in tags if t and t.strip())


def tags_from_db(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(t for t in (s.strip() for s in raw.split(",")) if t)


def row_to_resource(row) -> Resource:
    m = row._mapping
    return Resource(
        id=m["id"],
        slug=m["slug"],
        type=m["type"],
        display_name=m["display_name"],
        description=m.get("description"),
        tags=tags_from_db(m.get("tags")),
        active_version_id=m.get("active_version_id"),
        status=m.get("status") or "active",
        created_at=m["created_at"],
        updated_at=m["updated_at"],
        created_by=m.get("created_by"),
    )


def row_to_version(row) -> ResourceVersion:
    m = row._mapping
    return ResourceVersion(
        id=m["id"],
        resource_id=m["resource_id"],
        version_number=m["version_number"],
        is_draft=bool(m["is_draft"]),
        import_source=m["import_source"],
        source_metadata=json.loads(m["source_metadata"])
        if m.get("source_metadata")
        else None,
        content_hash=m["content_hash"],
        byte_size=int(m.get("byte_size") or 0),
        metadata=json.loads(m["metadata_json"]) if m.get("metadata_json") else None,
        changelog=m["changelog"],
        created_at=m["created_at"],
        created_by=m.get("created_by"),
    )


def row_to_blob(row) -> ResourceBlob:
    m = row._mapping
    return ResourceBlob(
        id=m["id"],
        resource_version_id=m["resource_version_id"],
        relative_path=m["relative_path"],
        content=m["content"],
        content_text=m.get("content_text"),
        mime_type=m.get("mime_type"),
        size_bytes=int(m.get("size_bytes") or 0),
    )
