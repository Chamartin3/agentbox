"""RunExecutor — orchestrates a single agent run end-to-end."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from agentbox.core.config import Settings
from agentbox.core.data import AgentDef
from agentbox.core.db.database import Database
from agentbox.core.db.utils import now_iso
from agentbox.core.constants import RunStatus
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
from agentbox.core.execution.observability.snapshot import SnapshotWriter
from agentbox.core.execution.orchestrate.steploop import RunStepLoop
from agentbox.core.execution.prepare.prompts import resolve_run_prompt
from agentbox.core.execution.retry import pump_into_session  # noqa: F401
from agentbox.core.engines.contracts.rendered import RenderedConfig
from agentbox.core.workspaces import (
    prepare_run_workdir,
)
from agentbox.core.workspaces import McpRegistry
from agentbox.core.workspaces.generation.inject import (
    inject_agent_tools_mcp,
    inject_host_env_mcp,
)

logger = logging.getLogger(__name__)


class RunExecutor:
    """High-level orchestrator. Owns task lifecycle; delegates phases."""

    def __init__(
        self,
        db: Database,
        settings: Settings,
        mcp_registry: "McpRegistry | None" = None,
    ):
        self.db = db
        self.settings = settings
        self._mcp_registry = mcp_registry
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
        agent: AgentDef,
        input_: str,
        session_id: str | None = None,
        workspace_override: str | None = None,
        timeout_seconds: int | None = None,
        webhook_url: str | None = None,
        runner_override: str | None = None,
        backend: str | None = None,
        variables: dict[str, Any] | None = None,
        runner_embedded: bool = False,
        runner_profile: str | None = None,
        runner_config: dict[str, Any] | None = None,
    ) -> str:
        workdir, session_id = self._setup.prepare_workdir(
            agent, session_id, workspace_override
        )
        if backend is None and runner_override is not None:
            backend = runner_override
        if webhook_url is not None:
            agent = agent.model_copy(update={"webhook_url": webhook_url})

        # ── Prompt / composition resolution (agents domain) ───────────────
        resolved = resolve_run_prompt(
            db=self.db,
            settings=self.settings,
            agent=agent,
            input_=input_,
            variables=variables,
        )
        agent = resolved.agent
        input_ = resolved.input_
        composed = resolved.to_composed_state()
        _prompt_snapshot_entries = resolved.snapshot_entries
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

        adapter, rendered = self._setup.select_backend(
            agent, workdir, backend, runner_config=effective, composed=composed
        )

        # ── Workspace materialization + run_dir creation ──────────────────
        run_dir, _workspace_snapshot_entries = prepare_run_workdir(
            workspace_file_resource_bindings=self.db.workspace_file_resource_bindings,
            resources=self.db.resources,
            resource_versions=self.db.resource_versions,
            resource_blobs=self.db.resource_blobs,
            workspace_env_doc_versions=self.db.workspace_env_doc_versions,
            workspace_runtime_permissions=self.db.workspace_runtime_permissions,
            workspaces=self.db.workspaces,
            agent_defs=self.db.agent_defs,
            workspace_subagents=self.db.workspace_subagents,
            agent_versions=self.db.agent_versions,
            workspace_mcp_overrides=self.db.workspace_mcp_overrides,
            workspace_mcp_tool_overrides=self.db.workspace_mcp_tool_overrides,
            settings=self.settings,
            workspace_id=_workspace_id,
            agent=agent,
            workdir=workdir,
            mcp_registry=self._mcp_registry,
            system_prompt=composed.system if composed else None,
        )
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

        _host_env_grants = self._snapshots.resolve_host_env_grants(_workspace_id)
        _agent_tool_grants = self._setup.resolve_agent_tool_grants(agent.id)
        if _host_env_grants:
            inject_host_env_mcp(
                run_dir=run_dir, grants=_host_env_grants,
                workspace_id=_workspace_id or "", workdir=workdir,
                db_path=self.settings.db_path,
            )
        if _agent_tool_grants:
            inject_agent_tools_mcp(
                run_dir=run_dir, grants=_agent_tool_grants,
                agent_id=agent.id, workdir=workdir,
                db_path=self.settings.db_path,
            )

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
            composed=composed, input_=input_,
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
            prepared_composed_result=resolved.composition_result,
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
            effective=effective, composed=composed,
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
