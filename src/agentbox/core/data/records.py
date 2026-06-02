"""DB return-shape dataclasses and TypedDicts for snapshots and non-run records.

RunRecord and its row mapper live in ``core.data.runs.records``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
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


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
