"""RunExecutor — orchestrates a single agent run end-to-end.

``RunExecutor`` is the composition root for the executor subsystem (UNIFIED
rule #4). It calls ``get_database`` once, then decomposes ``self.db`` into
concrete manager instances and passes those to its sub-components. No
``Database`` object crosses a sub-component boundary.
"""

from __future__ import annotations
from collections.abc import Callable
from typing import Any

import asyncio
import logging
import uuid

from agentbox.core.config import Settings
from agentbox.core.db.database import Database, get_database
from agentbox.core.data._util import now_iso
from agentbox.core.data.constants import RunStatus
from agentbox.core.engines.profiles import RunnerProfileResolver
from agentbox.core.execution.orchestrate._runner import _run as _run_loop
from agentbox.core.execution.observability.stream.broadcaster import RunBroadcaster
from agentbox.core.execution.orchestrate.cancel import cancel_run as _cancel_run_helper
from agentbox.core.execution.orchestrate.finalizer import RunFinalizer
from agentbox.core.execution.orchestrate.init_run import (
    InitRunManagers,
    fail_pre_run as _fail_pre_run_fn,
    init_run,
    launch_background_task,
)
from agentbox.core.execution.orchestrate.setup import (
    NoBackendAvailable,
    RunSetup,
    SetupManagers,
)
from agentbox.core.data.composition import ComposedPrompt, RunSpec
from agentbox.core.execution.observability.snapshot import SnapshotManagers, SnapshotWriter
from agentbox.core.execution.orchestrate.steploop import RunStepLoop
from agentbox.core.execution.retry import pump_into_session  # noqa: F401
from agentbox.core.data import McpServerSpec, RenderedConfig
from agentbox.core.workspaces import Workspaces
from agentbox.core.mcp.registry import McpRegistry
from agentbox.core.workspaces.tooling.servers import resolve_workspace_mcp_helper
from agentbox.core.db.config import load_project_mcp_servers
from agentbox.core.data.constants import AGENT_TOOLS_SERVER_NAME, HOST_ENV_SERVER_NAME
from agentbox.core.data.payload_types import ExternalMcpServer, McpStdioServerSpec
from agentbox.core.tools.mcp_servers.specs import (
    agent_tools_server_spec,
    host_env_server_spec,
)

logger = logging.getLogger(__name__)


class RunExecutor:
    """High-level orchestrator. Owns task lifecycle; delegates phases."""

    def __init__(
        self,
        settings: Settings,
        mcp_registry: "McpRegistry | None" = None,
        *,
        db: Database | None = None,
        resolve_workspace_creds: Callable[[str], dict[str, str] | None] | None = None,
        project_mcp_servers: Callable[[], list[McpServerSpec]] | None = None,
    ) -> None:
        # Self-wire the store from settings (like Services); ``db`` stays an
        # optional injection point for tests. DI never opens the store.
        self.settings = settings
        self.db = db = db if db is not None else get_database(str(settings.db_path))
        self._mcp_registry = mcp_registry
        self._workspaces = Workspaces(db.workspace_read, settings)
        self._broadcasters: dict[str, RunBroadcaster] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._run_tasks: dict[str, asyncio.Task[None]] = {}
        self._profile_resolver = RunnerProfileResolver()
        # Decompose db into concrete manager bundles/params for sub-components.
        # No Database object crosses a sub-component boundary (UNIFIED rule #4).
        self._setup = RunSetup(
            SetupManagers(
                workspaces=db.workspaces,
                sessions=db.sessions,
                agent_tool_grants=db.agent_tool_grants,
                workspace_file_resource_bindings=db.workspace_file_resource_bindings,
                workspace_mcp_policies=db.workspace_mcp_policies,
                workspace_mcp_overrides=db.workspace_mcp_overrides,
                workspace_mcp_tool_overrides=db.workspace_mcp_tool_overrides,
                agent_prompt_resource_bindings=db.agent_prompt_resource_bindings,
                resource_versions=db.resource_versions,
                resource_blobs=db.resource_blobs,
            ),
            settings,
            mcp_registry,
            resolve_workspace_creds=resolve_workspace_creds,
            project_mcp_servers=project_mcp_servers,
        )
        self._snapshots = SnapshotWriter(
            SnapshotManagers(
                runs=db.runs,
                agent_host_env_grants=db.agent_host_env_grants,
                workspace_mcp_policies=db.workspace_mcp_policies,
                workspace_mcp_overrides=db.workspace_mcp_overrides,
                workspace_mcp_tool_overrides=db.workspace_mcp_tool_overrides,
            )
        )
        self._step_loop = RunStepLoop(usage=db.usage, settings=settings)
        self._finalizer = RunFinalizer(
            runs=db.runs,
            usage=db.usage,
            webhook_deliveries=db.webhook_deliveries,
            settings=settings,
        )
        self._init_run_managers = InitRunManagers(
            runs=db.runs,
            agent_versions=db.agent_versions,
            usage=db.usage,
            run_prompts=db.run_prompts,
            runner_profiles=db.runner_profiles,
        )

    def broadcaster(self, run_id: str) -> RunBroadcaster | None:
        return self._broadcasters.get(run_id)

    # ------------------------------------------------------------------ execute
    async def execute(
        self,
        composed: ComposedPrompt,
        *,
        variables: dict[str, Any] | None = None,
        session_id: str | None = None,
        workspace_override: str | None = None,
        timeout_seconds: int | None = None,
        runner_override: str | None = None,
        backend: str | None = None,
        runner_embedded: bool = False,
        runner_profile: str | None = None,
        runner_config: dict[str, Any] | None = None,
        fresh_workspace: bool = False,
        session_mode: str | None = None,
    ) -> str:
        """Drive a single run from an already-composed prompt.

        The prompt was composed at run creation (service layer); this method
        never builds one. It resolves the dispatch statics (workdir, engine,
        timeout) into a :class:`RunSpec`, then drives the engine + retry loop.
        Any ``webhook_url`` is already baked into ``composed.agent``.
        """
        assert composed.agent is not None
        agent = composed.agent
        input_ = composed.input_

        workdir, session_id, dispose_workdir = self._setup.prepare_workdir(
            agent, session_id, workspace_override,
            session_mode=session_mode, fresh_workspace=fresh_workspace,
        )
        if backend is None and runner_override is not None:
            backend = runner_override

        composed_state = composed.to_composed_state()
        _prompt_snapshot_entries = composed.snapshot_entries
        # Prefer the run-requested workspace (same source prepare_workdir used
        # for the workdir); fall back to the agent's bound workspace.
        _ws_from_agent = agent.workspace if agent.workspace != "<ephemeral>" else None
        _workspace_id = workspace_override or _ws_from_agent

        try:
            effective = self._profile_resolver.resolve(
                agent=agent,
                runner_profiles=self.db.runner_profiles,
                runner_profile_id=runner_profile,
                runner_config=runner_config,
                backend_override=backend,
                timeout_seconds=timeout_seconds,
            )
        except ValueError as exc:
            return _fail_pre_run_fn(
                self._init_run_managers.runs,
                self.settings,
                self._broadcasters,
                agent=agent, input_=input_, workdir=workdir,
                session_id=session_id, error_msg=str(exc),
            )

        if effective.backend is None and backend is None:
            return _fail_pre_run_fn(
                self._init_run_managers.runs,
                self.settings,
                self._broadcasters,
                agent=agent, input_=input_, workdir=workdir,
                session_id=session_id,
                error_msg=(
                    f"agent {agent.id!r} has no runner profile bound. "
                    "Assign a runner profile in the UI (Agents → Runner Profile)."
                ),
            )

        # Execution's complete input contract — composed prompt (built at run
        # creation) + the resolved dispatch statics. Assembled once here.
        spec = RunSpec(
            composed=composed,
            engine_name=effective.backend or backend or "",
            input_=input_,
            workdir=workdir,
            timeout_seconds=int(
                effective.timeout_seconds or agent.runner.timeout_seconds
            ),
        )

        adapter, rendered = self._setup.select_backend(
            agent, spec.workdir, backend, runner_config=effective, composed=composed_state
        )

        # ── Workspace materialization + run_dir creation ──────────────────
        # No bound workspace → the agent itself acts as a single-agent
        # workspace so its own config still renders into the run dir
        # (parity with the old prep.py:400 `else agent.id` fallback).
        _wsid = (
            _workspace_id
            if _workspace_id and _workspace_id != "<ephemeral>"
            else agent.id
        )
        run_dir = self.settings.runs_tmpfs_dir / uuid.uuid4().hex
        run_dir.mkdir(mode=0o700, parents=True, exist_ok=False)

        # Run-scoped intrinsic MCP servers: build their spawn specs from the
        # resolved grants + run context, then let build() write them into the
        # run dir's .mcp.json alongside every other server — one writer, no
        # post-render patch.
        _host_env_grants = self._snapshots.resolve_host_env_grants(agent.id)
        _agent_tool_grants = self._setup.resolve_agent_tool_grants(agent.id)
        _extra_mcp: dict[str, McpStdioServerSpec] = {}
        if _host_env_grants:
            _extra_mcp[HOST_ENV_SERVER_NAME] = host_env_server_spec(
                grants=_host_env_grants,
                workspace_id=_workspace_id or "",
                workdir=workdir,
                db_path=self.settings.db_path,
            )
        if _agent_tool_grants:
            _extra_mcp[AGENT_TOOLS_SERVER_NAME] = agent_tools_server_spec(
                grants=_agent_tool_grants,
                agent_id=agent.id,
                workdir=workdir,
                db_path=self.settings.db_path,
            )

        _build = self._workspaces.build(
            _wsid,
            into=run_dir,
            # This run uses exactly one engine; the fresh run dir needs only its
            # config, not every installed engine's.
            engines=(spec.engine_name,) if spec.engine_name else None,
            system_prompt=composed_state.system if composed_state else None,
            extra_mcp_servers=_extra_mcp or None,
        )
        _workspace_snapshot_entries = _build.snapshot_entries
        # ── Resolve cwd relative to run_dir ───────────────────────────────
        _raw_cwd = rendered.cwd
        if not _raw_cwd.is_absolute():
            _raw_cwd = run_dir / _raw_cwd
        # Option B: thread grants env vars from each intrinsic MCP spec into the
        # opencode subprocess env so the servers it spawns inherit the grants.
        # Grants are shared globally across all MCP children — per-server
        # isolation needs McpLocal.environment if required later.
        _mcp_env: dict[str, str] = {}
        for _spec in _extra_mcp.values():
            for _k, _v in (_spec.get("env") or {}).items():
                if isinstance(_v, str):
                    _mcp_env[_k] = _v
        _merged_env = dict(rendered.env)
        _merged_env.update(_mcp_env)
        rendered = RenderedConfig(
            argv=rendered.argv,
            env=_merged_env,
            cwd=_raw_cwd,
            agent_meta=rendered.agent_meta,
            model=rendered.model,
        )
        _resource_snapshot_entries = _prompt_snapshot_entries + _workspace_snapshot_entries

        if _host_env_grants:
            rendered.agent_meta["agent_id"] = agent.id
            rendered.agent_meta["host_env_grants"] = _host_env_grants
            rendered.agent_meta["agent_tool_grants"] = (
                sorted(_agent_tool_grants) if _agent_tool_grants else None
            )
            rendered.agent_meta["host_env_workspace_id"] = _workspace_id or ""
            rendered.agent_meta["host_env_workdir"] = str(workdir)
            rendered.agent_meta["host_env_db_path"] = str(self.settings.db_path)

        # External (project/workspace-attached) MCP servers → thread to backends
        # that read agent_meta (the token direct path). Config-file backends
        # (claude_code/opencode) already receive these via the workspace build;
        # this closes the gap so every harness can invoke external MCP tools.
        try:
            _project = load_project_mcp_servers(db=self.db)
            _manifest = [
                {"name": s.name, "config": s.model_dump(exclude={"name"})}
                for s in _project
            ]
            _resolved_mcp = resolve_workspace_mcp_helper(
                self.db.workspace_mcp_policies,
                self.db.workspace_mcp_overrides,
                self.db.workspace_mcp_tool_overrides,
                _wsid,
                _manifest,
            )
            _external_mcp: list[ExternalMcpServer] = [
                {
                    "name": s["name"],
                    "config": s.get("config") or {},
                    "disabled_tools": s.get("disabled_tools") or [],
                }
                for s in _resolved_mcp.get("servers", [])
                if s.get("enabled")
            ]
        except Exception:
            logger.debug("external MCP resolution failed", exc_info=True)
            _external_mcp = []
        if _external_mcp:
            rendered.agent_meta["external_mcp_servers"] = _external_mcp
            # Exposure-time scoping: granted tool names (empty grants → no
            # agent-level restriction, mirroring host-env semantics).
            rendered.agent_meta["external_mcp_allowed_tools"] = (
                sorted(_agent_tool_grants) if _agent_tool_grants else None
            )

        transcripts_dir = self.settings.data_dir / "transcripts"
        transcripts_dir.mkdir(parents=True, exist_ok=True)
        transcript_path = transcripts_dir / f"{uuid.uuid4().hex}.jsonl"
        run_id = uuid.uuid4().hex
        self.db.runs.create(
            id=run_id,
            agent_id=agent.id,
            input=input_,
            workdir=str(workdir),
            transcript_path=str(transcript_path),
            session_id=session_id,
            status=RunStatus.RUNNING.value,
            created_at=now_iso(),
            config_digest=rendered.digest,
            runner_profile_id=effective.profile_id,
        )

        init_run(
            run_id=run_id, agent=agent, managers=self._init_run_managers,
            settings=self.settings, adapter=adapter, rendered=rendered,
            composed=spec.composed, input_=spec.input_,
            transcript_path=transcript_path,
            _snapshots=self._snapshots, _setup=self._setup,
            effective=effective,
            backend_override=backend,
            runner_override=runner_override,
            runner_profile=runner_profile,
            runner_config=runner_config,
            timeout_override=timeout_seconds,
            workspace_id=_workspace_id,
            resource_snapshot_entries=_resource_snapshot_entries,
            prepared_composed_result=spec.composed.composition_result,
            variables=variables,
        )

        if runner_embedded:
            if variables:
                self.db.runs.save_composition(
                    run_id=run_id, composition_snapshot=None,
                    rendered_prompt=None, variables=variables,
                )
            return run_id

        launch_background_task(
            run_id=run_id, adapter=adapter, rendered=rendered,
            agent=agent, input_=input_, workdir=workdir, run_dir=run_dir,
            transcript_path=transcript_path,
            managers=self._init_run_managers, settings=self.settings,
            effective=effective, composed=spec.composed,
            step_loop=self._step_loop, finalizer=self._finalizer,
            _run_loop=_run_loop,
            broadcasters=self._broadcasters,
            tasks=self._tasks, run_tasks=self._run_tasks,
            dispose_workdir=dispose_workdir,
        )
        return run_id

    # ------------------------------------------------------------------ cancel
    async def cancel_run(self, run_id: str) -> bool:
        """Cancel an in-progress run."""
        return _cancel_run_helper(
            run_id=run_id,
            runs=self.db.runs,
            agent_defs=self.db.agent_defs,
            usage=self.db.usage,
            webhook_deliveries=self.db.webhook_deliveries,
            broadcasters=self._broadcasters,
            run_tasks=self._run_tasks,
            settings=self.settings,
        )

__all__ = [
    "NoBackendAvailable",
    "RunBroadcaster",
    "RunExecutor",
    "pump_into_session",
]
