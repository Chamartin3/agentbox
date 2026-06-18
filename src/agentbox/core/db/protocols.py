"""Store protocol surfaces used by the executor.

These are runtime-checkable Protocols that define the minimal store
surface each layer needs — the executor, startup hooks, and workspace
build.  They exist so callers can depend on the contract rather than the
concrete SessionStore.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol, runtime_checkable

from sqlalchemy.engine import Engine as _Engine

from agentbox.core.db.agents.manifest import AgentDef
from agentbox.core.db.engines.profiles import RunnerProfile
from agentbox.core.db.execution.records import RunRecord
from agentbox.core.db.execution.snapshots import (
    McpSnapshot,
    ResourceSnapshotEntry,
    RunnerSnapshot,
)
from agentbox.core.db.row_types import EnvDocRow, RepoResourceRow, WorkspaceRow
from agentbox.core.db.workspaces.manifest import McpServerSpec


@runtime_checkable
class RunStore(Protocol):
    """Minimal store surface needed by the executor.

    Widened to cover RunSetupStore, SnapshotStore, WorkspaceBuildStore,
    and the additional SessionStore surface consumed by WebhookDispatcher,
    prepare_run_resources, build_runner_snapshot, build_fragments, and
    _fail_pre_run_fn — so that passing a RunStore-typed value to any
    of those collaborators passes pyright without ``# type: ignore``.
    """

    engine: _Engine

    # ------------------------------------------------------------------
    # Run lifecycle
    # ------------------------------------------------------------------

    def create_run(
        self,
        agent_id: str,
        input_: str,
        workdir: str,
        transcript_path: str,
        session_id: str | None = None,
        config_digest: str | None = None,
        runner_profile_id: str | None = None,
    ) -> str: ...

    def finish_run(
        self,
        run_id: str,
        ok: bool,
        output: str | None = None,
        error: str | None = None,
        status: str | None = None,
        validation_status: str | None = None,
        validation_errors: list[str] | None = None,
        schema_validated_via: str | None = None,
    ) -> None: ...

    def set_run_status(self, run_id: str, status: str) -> None: ...

    def set_run_conversation(
        self,
        run_id: str,
        conversation_format: str | None,
        conversation_uri: str | None = None,
    ) -> None: ...

    def get_run(self, run_id: str) -> RunRecord | None: ...

    # ------------------------------------------------------------------
    # Run snapshots
    # ------------------------------------------------------------------

    def save_run_snapshot(
        self,
        run_id: str,
        rendered_prompt: dict,
        variables: dict,
        validation_status: str,
        validation_errors: list[str],
        composition_snapshot: dict | None = None,
    ) -> None: ...

    def save_run_composition(
        self,
        run_id: str,
        composition_snapshot: dict | None,
        rendered_prompt: dict | None,
        variables: dict | None,
    ) -> None: ...

    def save_resource_snapshots(
        self,
        run_id: str,
        *,
        resource_snapshot: list[ResourceSnapshotEntry] | None = None,
        mcp_snapshot: McpSnapshot | None = None,
    ) -> None: ...

    def save_run_runner_snapshot(
        self, run_id: str, runner_snapshot: RunnerSnapshot
    ) -> None: ...

    def save_run_prompt(self, run_id: str, fragments_json: str) -> None: ...

    # ------------------------------------------------------------------
    # Runner profile
    # ------------------------------------------------------------------

    def get_runner_profile(self, profile_id: str) -> RunnerProfile | None: ...

    # ------------------------------------------------------------------
    # Usage / webhook
    # ------------------------------------------------------------------

    def record_usage(self, run_id: str, payload: dict) -> None: ...

    def get_usage(self, run_id: str) -> dict | None: ...

    def record_webhook_delivery(
        self,
        run_id: str,
        attempt: int,
        url: str,
        payload: dict | None = None,
        response_status: int | None = None,
        response_body: str | None = None,
        latency_ms: int | None = None,
        error: str | None = None,
    ) -> None: ...

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    def get_session(self, session_id: str) -> dict | None: ...

    def touch_session(self, session_id: str) -> None: ...

    def create_session(
        self, agent_id: str, mode: str, workdir: str | None
    ) -> str: ...

    def set_session_workdir(
        self, session_id: str, workdir: str
    ) -> None: ...

    # ------------------------------------------------------------------
    # Agent / version
    # ------------------------------------------------------------------

    def get_active_version(self, agent_id: str) -> dict | None: ...

    def latest_version(self, agent_id: str) -> dict | None: ...

    def get_agent_def(self, agent_id: str) -> AgentDef | None: ...

    def get_latest_committed_prompt(self, agent_id: str) -> dict | None: ...

    def list_active_grants(self, agent_id: str) -> set[str]: ...

    def list_version_files(self, version_id: int) -> list[dict]: ...

    # ------------------------------------------------------------------
    # Workspace resources
    # ------------------------------------------------------------------

    def get_workspace_runtime_permissions(
        self, workspace_id: str
    ) -> dict | None: ...

    def list_workspace_file_bindings(
        self, workspace_id: str
    ) -> list[dict]: ...

    def get_repo_resource(self, resource_id: str) -> RepoResourceRow | None: ...

    def get_active_repo_version(self, resource_id: str) -> dict | None: ...

    def get_repo_version(self, version_id: str) -> dict | None: ...

    def iter_repo_blobs(self, version_id: str) -> Iterator[dict]: ...

    def resolve_workspace_host_env(self, workspace_id: str) -> dict: ...

    # ------------------------------------------------------------------
    # MCP / tooling
    # ------------------------------------------------------------------

    def get_project_mcp_servers(self) -> list[McpServerSpec]: ...

    def get_tool_manifest_path(self) -> str | None: ...

    def resolve_workspace_mcp(
        self,
        workspace_id: str,
        manifest_servers: list[dict],
        *,
        discovered_tools: dict[str, list[str]] | None = None,
    ) -> McpSnapshot: ...

    # ------------------------------------------------------------------
    # Workspace build surface (WorkspaceBuildStore)
    # ------------------------------------------------------------------

    def get_workspace(self, name: str) -> WorkspaceRow | None: ...

    def get_repo_resource_by_slug(self, slug: str) -> dict | None: ...

    def get_workspace_mcp_policy(self, workspace_id: str) -> str: ...

    def list_workspace_mcp_server_overrides(
        self, workspace_id: str
    ) -> list[dict]: ...

    def list_workspace_mcp_tool_overrides(
        self, workspace_id: str
    ) -> list[dict]: ...

    # ------------------------------------------------------------------
    # Subagents / env-doc
    # ------------------------------------------------------------------

    def list_workspace_subagents(
        self, workspace_id: str
    ) -> list[dict]: ...

    def get_active_env_doc(
        self, workspace_id: str
    ) -> EnvDocRow | None: ...

    # ------------------------------------------------------------------
    # Prompt bindings
    # ------------------------------------------------------------------

    def list_prompt_bindings(self, agent_id: str) -> list[dict]: ...

    def get_project_shared_assets(self) -> dict[str, str]: ...


@runtime_checkable
class StartupStore(Protocol):
    """Minimal store surface needed at startup."""

    def seed_default_runner_profiles(self, store: object) -> int: ...

    def backfill_workspaces_from_satellites(self) -> int: ...

    def prune_phantom_workspaces(self, keep: set[str]) -> list[str]: ...

    def set_agent_runner_profile(
        self, agent_id: str, profile_id: str
    ) -> object: ...

    def get_agent_runner_profile(self, agent_id: str) -> object | None: ...

    def get_system_default_runner_profile(self) -> object | None: ...


@runtime_checkable
class WorkspaceLookupStore(Protocol):
    """Minimal store surface for resolving a workspace by name."""

    def get_workspace(self, name: str) -> WorkspaceRow | None: ...


@runtime_checkable
class RunSetupStore(Protocol):
    """Minimal store surface needed by the run-setup layer."""

    def get_workspace(self, name: str) -> WorkspaceRow | None: ...

    def get_workspace_runtime_permissions(
        self, workspace_id: str
    ) -> dict | None: ...

    def get_session(self, session_id: str) -> dict | None: ...

    def touch_session(self, session_id: str) -> None: ...

    def create_session(
        self, agent_id: str, mode: str, workdir: str | None
    ) -> str: ...

    def set_session_workdir(
        self, session_id: str, workdir: str
    ) -> None: ...

    def list_active_grants(self, agent_id: str) -> set[str]: ...

    def get_project_mcp_servers(self) -> list[McpServerSpec]: ...

    def get_tool_manifest_path(self) -> str | None: ...

    def create_run(
        self,
        agent_id: str,
        input_: str,
        workdir: str,
        transcript_path: str,
        session_id: str | None = None,
        config_digest: str | None = None,
        runner_profile_id: str | None = None,
    ) -> str: ...

    def finish_run(
        self,
        run_id: str,
        ok: bool,
        output: str | None = None,
        error: str | None = None,
        status: str | None = None,
        validation_status: str | None = None,
        validation_errors: list[str] | None = None,
        schema_validated_via: str | None = None,
    ) -> None: ...


@runtime_checkable
class SnapshotStore(Protocol):
    """Minimal store surface needed by the snapshot-writing layer."""

    def get_runner_profile(self, profile_id: str) -> RunnerProfile | None: ...

    def save_run_runner_snapshot(
        self, run_id: str, runner_snapshot: RunnerSnapshot
    ) -> None: ...

    def get_project_mcp_servers(self) -> list[McpServerSpec]: ...

    def resolve_workspace_mcp(
        self,
        workspace_id: str,
        manifest_servers: list[dict],
        *,
        discovered_tools: dict[str, list[str]] | None = None,
    ) -> McpSnapshot: ...

    def save_resource_snapshots(
        self,
        run_id: str,
        *,
        resource_snapshot: list[ResourceSnapshotEntry] | None = None,
        mcp_snapshot: McpSnapshot | None = None,
    ) -> None: ...

    def resolve_workspace_host_env(
        self, workspace_id: str
    ) -> dict: ...


@runtime_checkable
class UsageStore(Protocol):
    """Minimal store surface needed by the step-loop for usage recording."""

    def record_usage(self, run_id: str, payload: dict) -> None: ...


@runtime_checkable
class WorkspaceBuildStore(Protocol):
    """Minimal store surface needed by workspace build."""

    def get_workspace(self, name: str) -> WorkspaceRow | None: ...

    def get_repo_resource_by_slug(self, slug: str) -> dict | None: ...

    def get_repo_resource(self, resource_id: str) -> RepoResourceRow | None: ...

    def list_workspace_file_bindings(
        self, workspace_id: str
    ) -> list[dict]: ...

    def get_active_repo_version(self, resource_id: str) -> dict | None: ...

    def iter_repo_blobs(self, version_id: str) -> Iterator[dict]: ...

    def resolve_workspace_host_env(
        self, workspace_id: str
    ) -> dict: ...

    def get_workspace_runtime_permissions(
        self, workspace_id: str
    ) -> dict | None: ...

    def get_workspace_mcp_policy(self, workspace_id: str) -> str: ...

    def list_workspace_mcp_server_overrides(
        self, workspace_id: str
    ) -> list[dict]: ...

    def list_workspace_mcp_tool_overrides(
        self, workspace_id: str
    ) -> list[dict]: ...

    def list_workspace_subagents(
        self, workspace_id: str
    ) -> list[dict]: ...

    def get_active_env_doc(self, workspace_id: str) -> EnvDocRow | None: ...

    def get_active_version(self, agent_id: str) -> dict | None: ...

    def get_agent_def(self, agent_id: str) -> AgentDef | None: ...

    def get_repo_version(self, version_id: str) -> dict | None: ...
