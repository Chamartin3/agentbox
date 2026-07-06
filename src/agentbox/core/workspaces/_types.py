"""Concrete TypedDict shapes for core/workspaces domain.

These are internal return types for workspace-related functions.
Cross-domain shapes go in core/data/payload_types.py.
"""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict

from agentbox.core.data.payload_types import GrantConfig, McpStdioServerSpec


# ── MCP Client responses ──


class McpInitializeResult(TypedDict):
    """MCP initialize response — server capabilities and protocol version."""

    protocolVersion: str
    capabilities: dict[str, Any]
    serverInfo: dict[str, Any]


class McpToolsListResult(TypedDict):
    """MCP tools/list response."""

    tools: list[dict[str, Any]]


# ── Health/status ──


class ServerHealthDict(TypedDict):
    """Single MCP server's health status (for serialization)."""

    status: str  # "ok" | "degraded" | "unavailable"
    tool_count: int
    fetched_at: NotRequired[str | None]
    last_error: NotRequired[str | None]


class McpHealthReportDict(TypedDict):
    """Serialized MCP health report."""

    status: str
    mcp_servers: dict[str, ServerHealthDict]


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


# ── Host-env tools ──


# ── Workspace resource resolution ──


class WorkspaceResourceBinding(TypedDict):
    """Hydrated workspace resource binding (materializer-ready)."""

    binding_id: str
    resource_id: str
    version_id: str
    content_hash: str
    type: str
    slug: str
    display_name: str
    target_path: str | None
    materialize_mode: str
    on_conflict: str
    blobs: list[Any]
    skill_meta: None
    source_metadata: dict[str, Any]


class WorkspaceSubagentBinding(TypedDict):
    """Hydrated workspace subagent (renderer-ready)."""

    workspace_id: str
    agent_id: str
    alias: str
    description: str | None
    prompt_content: str


class WorkspacePermissions(TypedDict, total=False):
    """Workspace runtime permission overlay."""

    allowed_builtin_tools: list[str] | None
    files: list[Any] | None
    max_tokens: int | None
    allow_file_write: bool | None
    allow_network: bool | None


# ── MCP server specs for injection ──


class McpConfigData(TypedDict, total=False):
    """MCP configuration file data."""

    mcpServers: dict[str, McpStdioServerSpec]


# ── Workspace build/sync ──


class WorkspaceSyncMeta(TypedDict, total=False):
    """Workspace sync provenance metadata."""

    workspace_id: str
    synced_at: str
    env_doc_files: list[str]
    subagents_written: list[str]
    bindings_materialized: int
    bindings_skipped: int
    materialized_paths: list[str]
    orphans_removed: list[str]
    errors: list[str]
