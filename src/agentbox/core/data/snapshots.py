"""Snapshot TypedDicts captured during run dispatch — execution-domain shapes."""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict

from agentbox.core.data.composition import PromptResolution
from agentbox.core.data.payload_types import (
    PromptEmbedSnapshotEntry,
    WorkspaceFileSnapshotEntry,
)
from agentbox.core.data.workenv import MaterializeOutcome


def workspace_outcomes_to_snapshot(outcomes: list[MaterializeOutcome]) -> list[WorkspaceFileSnapshotEntry]:
    """Convert MaterializeOutcome list to JSON-serializable snapshot entries."""
    entries: list[WorkspaceFileSnapshotEntry] = []
    for o in outcomes:
        entries.append(
            {
                "role": "workspace_file",
                "binding_id": o.binding_id,
                "resource_id": o.resource_id,
                "version_id": o.version_id,
                "content_hash": o.content_hash,
                "target_path": o.target_path,
                "files_written": o.files_written,
                "mode": o.mode,
                "skipped": o.skipped,
                "skipped_reason": o.skipped_reason,
            }
        )
    return entries


def prompt_resolution_to_snapshot(resolution: PromptResolution) -> list[PromptEmbedSnapshotEntry]:
    """Convert PromptResolution snapshot list to JSON-serializable entries."""
    entries: list[PromptEmbedSnapshotEntry] = []
    for rb in resolution.snapshot:
        entries.append(
            {
                "role": "prompt_embed",
                "binding_id": rb.binding_id,
                "marker": rb.marker,
                "resource_id": rb.resource_id,
                "version_id": rb.version_id,
                "content_hash": rb.content_hash,
                "mode": rb.mode,
            }
        )
    return entries





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
