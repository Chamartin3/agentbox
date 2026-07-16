"""RunExecutor — orchestrates a single agent run end-to-end."""

from __future__ import annotations
from typing import Any

import asyncio
import logging
import uuid

from agentbox.core.config import Settings
from agentbox.core.db.database import Database
from agentbox.core.data._util import now_iso
from agentbox.core.data.constants import RunStatus
from agentbox.core.engines.profiles import RunnerProfileResolver
from agentbox.core.execution.orchestrate._runner import _run as _run_loop
from agentbox.core.execution.observability.stream.broadcaster import RunBroadcaster
from agentbox.core.execution.orchestrate.cancel import cancel_run as _cancel_run_helper
from agentbox.core.execution.orchestrate.finalizer import RunFinalizer
from agentbox.core.execution.orchestrate.init_run import (
    fail_pre_run as _fail_pre_run_fn,
    init_run,
    launch_background_task,
)
from agentbox.core.execution.orchestrate.setup import (
    NoBackendAvailable,
    RunSetup,
)
from agentbox.core.data.composition import ComposedPrompt, RunSpec
from agentbox.core.execution.observability.snapshot import SnapshotWriter
from agentbox.core.execution.orchestrate.steploop import RunStepLoop
from agentbox.core.execution.retry import pump_into_session  # noqa: F401
from agentbox.core.data import RenderedConfig
from agentbox.core.workspaces import Workspaces
from agentbox.core.workspaces.tooling.mcp.registry import McpRegistry
from agentbox.core.data.constants import AGENT_TOOLS_SERVER_NAME, HOST_ENV_SERVER_NAME
from agentbox.core.data.payload_types import McpStdioServerSpec
from agentbox.core.tools.mcp_servers.specs import (
    agent_tools_server_spec,
    host_env_server_spec,
)

logger = logging.getLogger(__name__)


class RunExecutor:
    """High-level orchestrator. Owns task lifecycle; delegates phases."""

    def __init__(
        self,
        db: Database,
        settings: Settings,
        mcp_registry: "McpRegistry | None" = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self._mcp_registry = mcp_registry
        self._workspaces = Workspaces(db.workspace_read, settings)
        self._broadcasters: dict[str, RunBroadcaster] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._run_tasks: dict[str, asyncio.Task[None]] = {}
        self._profile_resolver = RunnerProfileResolver()
        self._setup = RunSetup(db, settings, mcp_registry)
        self._snapshots = SnapshotWriter(db)
        self._step_loop = RunStepLoop(db, settings)
        self._finalizer = RunFinalizer(db, settings)

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

        workdir, session_id = self._setup.prepare_workdir(
            agent, session_id, workspace_override
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
                self.db,
                self.settings,
                self._broadcasters,
                agent=agent, input_=input_, workdir=workdir,
                session_id=session_id, error_msg=str(exc),
            )

        if effective.backend is None and backend is None:
            return _fail_pre_run_fn(
                self.db,
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
        rendered = RenderedConfig(
            argv=rendered.argv,
            env=rendered.env,
            cwd=_raw_cwd,
            agent_meta=rendered.agent_meta,
            model=rendered.model,
        )
        _resource_snapshot_entries = _prompt_snapshot_entries + _workspace_snapshot_entries

        if _host_env_grants:
            rendered.agent_meta["host_env_grants"] = _host_env_grants
            rendered.agent_meta["agent_tool_grants"] = (
                sorted(_agent_tool_grants) if _agent_tool_grants else None
            )
            rendered.agent_meta["host_env_workspace_id"] = _workspace_id or ""
            rendered.agent_meta["host_env_workdir"] = str(workdir)
            rendered.agent_meta["host_env_db_path"] = str(self.settings.db_path)

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
            run_id=run_id, agent=agent, db=self.db,
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
            db=self.db, settings=self.settings,
            effective=effective, composed=spec.composed,
            step_loop=self._step_loop, finalizer=self._finalizer,
            _run_loop=_run_loop,
            broadcasters=self._broadcasters,
            tasks=self._tasks, run_tasks=self._run_tasks,
        )
        return run_id

    # ------------------------------------------------------------------ cancel
    async def cancel_run(self, run_id: str) -> bool:
        """Cancel an in-progress run."""
        return _cancel_run_helper(
            run_id=run_id,
            db=self.db,
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
