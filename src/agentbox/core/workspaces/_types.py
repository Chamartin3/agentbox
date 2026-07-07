"""Concrete TypedDict shapes for the core/workspaces domain.

These are internal return types for workspace-related functions.
Cross-domain shapes go in core/data/payload_types.py.
"""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict

from agentbox.core.data.payload_types import GrantConfig


# ── Workspace MCP resolution ──


class WorkspaceMcpServerConfig(TypedDict):
    """Single server in resolved workspace MCP configuration."""

    name: str
    enabled: bool
    config: dict[str, Any] | None
    disabled_tools: list[str]
    source: str  # "default" | "override" | "override_only"


class WorkspaceMcpConfigResult(TypedDict):
    """Resolved workspace MCP server configuration."""

    servers: list[WorkspaceMcpServerConfig]
    policy: str | None


# ── Workspace host-env grants resolution ──


class WorkspaceHostEnvGrantsResult(TypedDict):
    """Resolved workspace host-env grants and profile."""

    grants: dict[str, GrantConfig]
    profile_id: str | None
    overrides: NotRequired[dict[str, GrantConfig] | None]


# ── Workspace build/sync provenance ──


class WorkspaceSyncMeta(TypedDict, total=False):
    """Workspace sync provenance metadata (``.agentbox/meta.json``)."""

    workspace_id: str
    synced_at: str
    env_doc_files: list[str]
    subagents_written: list[str]
    bindings_materialized: int
    bindings_skipped: int
    materialized_paths: list[str]
    orphans_removed: list[str]
    errors: list[str]
