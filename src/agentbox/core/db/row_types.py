"""TypedDict row shapes returned by store queries.

These are the row-level contracts for query results, not SQLAlchemy models.
"""

from enum import StrEnum
from typing import TypedDict


class EnvDocRow(TypedDict):
    id: str
    workspace_id: str
    version_number: int
    content_json: dict
    is_draft: int
    changelog: str
    created_at: str
    created_by: str | None


class PromptVersionRow(TypedDict):
    id: int
    agent_id: str
    version: int
    content: str
    author: str
    changelog: str
    is_draft: int
    content_hash: str | None
    created_at: str


class AgentVersionRow(TypedDict):
    """A row from ``agent_versions`` as returned by the agent-version reads.

    ``is_legacy`` is shaped to ``bool`` (the table stores 0/1).
    """

    id: int
    agent_id: str
    version: int
    source_path: str
    source_format: str
    content_snapshot: str
    prompt_snapshot: str
    content_hash: str
    author: str
    changelog: str
    is_legacy: bool
    created_at: str
    config_json: str | None
    prompt_content: str | None
    source: str
    resolved_tool_grants: list[str] | None


class RepoResourceRow(TypedDict):
    id: str
    slug: str
    type: str
    display_name: str
    description: str | None
    tags: str | None
    active_version_id: str | None
    status: str
    created_at: str
    updated_at: str
    created_by: str | None


class WorkspaceRow(TypedDict):
    name: str
    description: str | None
    path: str | None
    source: str
    created_at: str
    created_by: str | None
    updated_at: str


class AgentMetaRow(TypedDict):
    """A row from ``agent_meta`` as returned by agent-meta reads.

    ``export_to_disk`` is stored as 0/1 (int) — the table value, not a bool.
    """

    agent_id: str
    sync_mode: str
    export_to_disk: int
    source_path: str | None
    source_format: str | None
    created_at: str
    updated_at: str
    deleted_at: str | None
    disabled_at: str | None


class AgentToolGrantRow(TypedDict):
    """A row from ``agent_tool_grants``."""

    id: str
    agent_id: str
    tool_name: str
    changelog: str
    granted_at: str
    granted_by: str | None
    revoked_at: str | None
    revoked_by: str | None
    revoke_changelog: str | None


class AgentVersionCommentRow(TypedDict):
    """A row from ``agent_version_comments``."""

    id: int
    version_id: int
    author: str
    body: str
    created_at: str


class AgentVersionRatingRow(TypedDict):
    """A row from ``agent_version_ratings``."""

    version_id: int
    rating: int
    rater: str
    rated_at: str


class AgentVersionFileRow(TypedDict):
    """A row from ``agent_version_files``."""

    id: int
    version_id: int
    relative_path: str
    kind: str
    content: str
    sha256: str
    source_uri: str | None
    position: int
    created_at: str


class AgentSyncRow(TypedDict):
    """A row from ``agent_sync``."""

    agent_id: str
    proxy_path: str | None
    sync_mode: str
    sync_policy: str
    last_file_hash: str | None
    last_file_mtime: str | None
    last_sync_at: str | None


class AgentConfigEventRow(TypedDict):
    """A row from ``agent_config_events``."""

    id: int
    agent_id: str
    field: str
    from_value: str | None
    to_value: str | None
    author: str
    source: str
    created_at: str


class VersionFileUploadRow(TypedDict):
    """Result from :py:meth:`AgentService.upload_version_file`."""

    file: "AgentVersionFileRow"
    sha256: str
    size: int


class ResourceStatus(StrEnum):
    ACTIVE = "active"
    DELETED = "deleted"


class WorkspaceSource(StrEnum):
    MANIFEST = "manifest"
    DB = "db"
