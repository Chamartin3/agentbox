"""Snapshot TypedDicts captured during run dispatch — execution-domain shapes."""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict



class RunnerSnapshot(TypedDict):
    """Append-only snapshot of the runner config that executed a run."""

    profile_id: str | None
    profile_name: str | None
    backend: str | None
    model: str | None
    timeout_seconds: int | None
    provider: str | None
    extra_args: list[str]
    source: str | None
    overrides_applied: dict[str, Any]
    captured_at: str


class McpServerSnapshot(TypedDict):
    """Per-server entry inside ``McpSnapshot.servers``."""

    name: str
    enabled: bool
    config: dict[str, Any]
    disabled_tools: NotRequired[list[str]]


class McpSnapshot(TypedDict):
    """Effective workspace MCP configuration captured at run dispatch."""

    servers: list[McpServerSnapshot]
    policy: NotRequired[str]
    host_env_grants: NotRequired[list[str]]
    host_env_injected: NotRequired[bool]


class ResourceSnapshotEntry(TypedDict):
    """One repo_resource version bound into a run."""

    resource_id: str
    version: int
    kind: str
    name: str
    sha256: str


class HostEnvGrant(TypedDict):
    """A single resolved host_env capability grant."""

    capability: str
    value: NotRequired[str]
    secret_ref: NotRequired[str]
