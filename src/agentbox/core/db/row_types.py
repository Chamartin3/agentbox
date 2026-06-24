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


class ResourceStatus(StrEnum):
    ACTIVE = "active"
    DELETED = "deleted"


class WorkspaceSource(StrEnum):
    MANIFEST = "manifest"
    DB = "db"
