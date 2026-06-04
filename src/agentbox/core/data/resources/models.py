"""Resource dataclasses returned by ``ResourcesMixin``.

Plain frozen records — the mixin maps DB rows to these for callers.
"""

from __future__ import annotations

from dataclasses import dataclass, field

RESOURCE_TYPES = ("document", "folder", "skill", "schema", "script")
IMPORT_SOURCES = ("upload", "host_path", "toml_migration", "db_only")


@dataclass(frozen=True)
class Resource:
    id: str
    slug: str
    type: str
    display_name: str
    description: str | None
    tags: tuple[str, ...]
    active_version_id: str | None
    status: str
    created_at: str
    updated_at: str
    created_by: str | None = None


@dataclass(frozen=True)
class ResourceVersion:
    id: str
    resource_id: str
    version_number: int
    is_draft: bool
    import_source: str
    source_metadata: dict | None
    content_hash: str
    byte_size: int
    metadata: dict | None
    changelog: str
    created_at: str
    created_by: str | None = None


@dataclass(frozen=True)
class ResourceBlob:
    id: str
    resource_version_id: str
    relative_path: str
    content: bytes
    content_text: str | None
    mime_type: str | None
    size_bytes: int


@dataclass(frozen=True)
class ResourceSnapshotEntry:
    """One row in ``RunRecord.resource_snapshot``."""

    resource_id: str
    version_id: str
    content_hash: str
    role: str  # 'prompt_embed' | 'workspace_file' | future...
    metadata: dict = field(default_factory=dict)
