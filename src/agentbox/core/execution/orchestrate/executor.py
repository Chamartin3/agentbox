"""RunExecutor — orchestrates a single agent run end-to-end."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING, Any

from agentbox.config import Settings
from agentbox.core.data import AgentDef, RunStore
from agentbox.core.engines.profiles import RunnerProfileResolver
from agentbox.core.execution.orchestrate._runner import _run as _run_loop
from agentbox.core.execution.orchestrate.broadcaster import RunBroadcaster
from agentbox.core.execution.orchestrate.finalizer import RunFinalizer
from agentbox.core.execution.orchestrate.cancel import cancel_run as _cancel_run_helper
from agentbox.core.execution.orchestrate.init_run import init_run, launch_background_task
from agentbox.core.execution.orchestrate.mcp_inject import (
    inject_agent_tools_mcp as _inject_agent_tools_mcp_helper_fn,
    inject_host_env_mcp as _inject_host_env_mcp_helper_fn,
)
from agentbox.core.execution.orchestrate.pre_run import (
    fail_pre_run as _fail_pre_run_fn,
)
from agentbox.core.execution.orchestrate.setup import (
    NoBackendAvailable,
    RunSetup,
)
from agentbox.core.execution.orchestrate.snapshots import SnapshotWriter
from agentbox.core.execution.orchestrate.steploop import RunStepLoop
from agentbox.core.execution.prepare import prepare_run_resources
from agentbox.core.execution.retry import _adapter_run_into_session  # noqa: F401
from agentbox.core.execution.webhooks import WebhookDispatcher

if TYPE_CHECKING:
    from agentbox.core.workspaces import McpRegistry

logger = logging.getLogger(__name__)


class RunExecutor:
    """High-level orchestrator. Owns task lifecycle; delegates phases."""

    def __init__(
        self,
        store: RunStore,
        settings: Settings,
        mcp_registry: "McpRegistry | None" = None,
    ):
        self.store = store
        self.settings = settings
        self._mcp_registry = mcp_registry
        self._broadcasters: dict[str, RunBroadcaster] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._run_tasks: dict[str, asyncio.Task[None]] = {}
        self._profile_resolver = RunnerProfileResolver()
        self._setup = RunSetup(store, settings, mcp_registry)
        self._snapshots = SnapshotWriter(store)
        self._webhooks = WebhookDispatcher(store)
        self._step_loop = RunStepLoop(store, settings)
        self._finalizer = RunFinalizer(store, self._webhooks)

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

        prepared = prepare_run_resources(
            store=self.store,
            settings=self.settings,
            agent=agent,
            input_=input_,
            variables=variables,
            workdir=workdir,
        )
        agent = prepared.agent
        input_ = prepared.input_
        composed = prepared.composed
        _resource_snapshot_entries = prepared.resource_snapshot_entries
        _workspace_id = prepared.workspace_id

        try:
            effective = self._profile_resolver.resolve(
                agent=agent,
                store=self.store,
                runner_profile_id=runner_profile,
                runner_config=runner_config,
                backend_override=backend,
                timeout_seconds=timeout_seconds,
            )
        except ValueError as exc:
            return _fail_pre_run_fn(
                self.store,
                self.settings,
                self._broadcasters,
                agent=agent, input_=input_, workdir=workdir,
                session_id=session_id, error_msg=str(exc),
            )

        if effective.backend is None and backend is None:
            return _fail_pre_run_fn(
                self.store,
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
        rendered, run_dir = self._setup.render_for_run(
            adapter, agent, workdir, rendered
        )

        _host_env_grants = self._snapshots.resolve_host_env_grants(_workspace_id)
        _agent_tool_grants = self._setup.resolve_agent_tool_grants(agent.id)
        self._setup.post_render(
            adapter, rendered,
            run_dir=run_dir, workdir=workdir,
            workspace_id=_workspace_id, agent_id=agent.id,
            host_env_grants=_host_env_grants,
            agent_tool_grants=_agent_tool_grants,
        )

        transcripts_dir = self.settings.data_dir / "transcripts"
        transcripts_dir.mkdir(parents=True, exist_ok=True)
        transcript_path = transcripts_dir / f"{uuid.uuid4().hex}.jsonl"
        run_id = self.store.create_run(
            agent_id=agent.id, input_=input_,
            workdir=str(workdir),
            transcript_path=str(transcript_path),
            session_id=session_id,
            config_digest=rendered.digest,
            runner_profile_id=effective.profile_id,
        )

        init_run(
            run_id=run_id, agent=agent, store=self.store,
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
            prepared_composed_result=prepared.composed_result,
            variables=variables,
        )

        if runner_embedded:
            if variables:
                self.store.save_run_composition(
                    run_id=run_id, composition_snapshot=None,
                    rendered_prompt=None, variables=variables,
                )
            return run_id

        launch_background_task(
            run_id=run_id, adapter=adapter, rendered=rendered,
            agent=agent, input_=input_, workdir=workdir, run_dir=run_dir,
            transcript_path=transcript_path,
            store=self.store, settings=self.settings,
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
            store=self.store,
            broadcasters=self._broadcasters,
            run_tasks=self._run_tasks,
            webhooks=self._webhooks,
        )

    # ------------------------------------------------------------------ wrappers (preserved for external callers)
    def _inject_host_env_mcp(
        self, run_dir, grants, workspace_id, workdir
    ) -> None:
        _inject_host_env_mcp_helper_fn(
            run_dir=run_dir, grants=grants,
            workspace_id=workspace_id, workdir=workdir,
            db_path=self.settings.db_path,
        )

    def _inject_agent_tools_mcp(
        self, run_dir, grants, agent_id, workdir
    ) -> None:
        _inject_agent_tools_mcp_helper_fn(
            run_dir=run_dir, grants=grants,
            agent_id=agent_id, workdir=workdir,
            db_path=self.settings.db_path,
        )


__all__ = [
    "NoBackendAvailable",
    "RunBroadcaster",
    "RunExecutor",
    "_adapter_run_into_session",
]
