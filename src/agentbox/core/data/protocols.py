"""Store protocol surfaces used by the executor.

These are runtime-checkable Protocols that define the minimal store
surface each layer needs — the executor, startup hooks, and workspace
build.  They exist so callers can depend on the contract rather than the
concrete SessionStore.
"""

from typing import Protocol, runtime_checkable

from agentbox.core.data.row_types import EnvDocRow, RepoResourceRow, WorkspaceRow


@runtime_checkable
class RunStore(Protocol):
    """Minimal store surface needed by the executor."""

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
        resource_snapshot: list | None = None,
        mcp_snapshot: dict | None = None,
    ) -> None: ...

    def save_run_runner_snapshot(
        self, run_id: str, runner_snapshot: dict
    ) -> None: ...

    def save_run_prompt(self, run_id: str, fragments_json: str) -> None: ...

    def record_usage(self, run_id: str, payload: dict) -> None: ...

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

    def set_run_status(self, run_id: str, status: str) -> None: ...

    def set_run_conversation(
        self,
        run_id: str,
        conversation_format: str | None,
        conversation_uri: str | None = None,
    ) -> None: ...


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
class WorkspaceBuildStore(Protocol):
    """Minimal store surface needed by workspace build."""

    def get_workspace(self, name: str) -> WorkspaceRow | None: ...

    def get_repo_resource_by_slug(self, slug: str) -> dict | None: ...

    def get_repo_resource(self, resource_id: str) -> RepoResourceRow | None: ...

    def list_workspace_file_bindings(
        self, workspace_id: str
    ) -> list[dict]: ...

    def get_active_repo_version(self, resource_id: str) -> dict | None: ...

    def iter_repo_blobs(self, version_id: str) -> object: ...

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

    def get_agent_def(self, agent_id: str) -> object: ...

    def get_repo_version(self, version_id: str) -> dict | None: ...
