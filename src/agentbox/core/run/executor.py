"""RunExecutor — orchestrates a single agent run end-to-end.

Thin orchestrator that delegates each lifecycle phase to a dedicated
collaborator under :mod:`agentbox.core.run.execute`:

* :class:`~agentbox.core.run.execute.setup.RunSetup` — workdir,
  backend selection, render, post-render MCP injection.
* :class:`~agentbox.core.run.execute.snapshots.SnapshotWriter` —
  runner/MCP/resource snapshots persisted to the run row.
* :class:`~agentbox.core.run.execute.steploop.RunStepLoop` — drives
  the backend stream + guardrails into a terminal :class:`StepResult`.
* :class:`~agentbox.core.run.execute.finalizer.RunFinalizer` — terminal
  persist + webhook + cleanup (the ``finally`` block of the run task).
* :class:`~agentbox.core.run.execute.webhooks.WebhookDispatcher` —
  completion webhook delivery.
* :class:`~agentbox.core.run.execute.broadcaster.RunBroadcaster` —
  in-memory pub/sub for WS subscribers.

The public surface (``RunExecutor.execute``, ``cancel_run``,
``broadcaster``, plus the re-exported ``RunBroadcaster`` /
``NoBackendAvailable`` / ``_adapter_run_into_session`` names) is
preserved exactly — external callers and tests don't change.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agentbox.api.events import DoneEvent, LogEvent
from agentbox.config import Settings
from agentbox.core.agent.profiles import RunnerProfileResolver
from agentbox.core.constants import RunStatus
from agentbox.core.data import AgentDef, SessionStore
from agentbox.core.data import runs as _runs_table
from agentbox.core.agent.prompt.capture import build_fragments, fragments_to_json

# Re-exports — preserve the historical public surface of this module so
# downstream imports (tests, services, host_env) keep working.
from agentbox.core.run.execute.broadcaster import RunBroadcaster
from agentbox.core.run.execute.finalizer import RunFinalizer
from agentbox.core.run.execute.setup import (
    NoBackendAvailable,
    RunSetup,
    fail_pre_run as _fail_pre_run_helper,
)
from agentbox.core.run.post_render import (
    inject_agent_tools_mcp as _inject_agent_tools_mcp_helper,
    inject_host_env_mcp as _inject_host_env_mcp_helper,
)
from agentbox.core.run.execute.snapshots import (
    SnapshotWriter,
    build_runner_snapshot,
)
from agentbox.core.run.execute.steploop import RunStepLoop
from agentbox.core.run.execute.webhooks import WebhookDispatcher
from agentbox.core.run.prepare import prepare_run_resources
# ``_adapter_run_into_session`` is re-imported below for back-compat with
# tests that depend on it being importable from this module.
from agentbox.core.run.retry import _adapter_run_into_session  # noqa: F401

if TYPE_CHECKING:
    from agentbox.core.workspace.mcp.client.registry import McpRegistry

logger = logging.getLogger(__name__)


class RunExecutor:
    """High-level orchestrator. Owns task lifecycle; delegates phases."""

    def __init__(
        self,
        store: SessionStore,
        settings: Settings,
        mcp_registry: McpRegistry | None = None,
    ):
        self.store = store
        self.settings = settings
        self._mcp_registry = mcp_registry
        self._broadcasters: dict[str, RunBroadcaster] = {}
        # Strong references to in-flight run tasks. asyncio only holds
        # weak references to tasks, so without this set the GC can collect
        # a long-running run mid-flight, skipping the finally block that
        # persists final status and fires the webhook.
        self._tasks: set[asyncio.Task[None]] = set()
        # run_id → task lookup for operator cancellation. Kept in sync
        # with ``_tasks`` (entries removed on task completion).
        self._run_tasks: dict[str, asyncio.Task[None]] = {}
        # Runner profile resolver — cheap to instantiate, used on every run.
        self._profile_resolver = RunnerProfileResolver()

        # Collaborators (constructed once, reused across runs).
        self._setup = RunSetup(store, settings, mcp_registry)
        self._snapshots = SnapshotWriter(store)
        self._webhooks = WebhookDispatcher(store)
        self._step_loop = RunStepLoop(store, settings)
        self._finalizer = RunFinalizer(store, self._webhooks)

    # ------------------------------------------------------------------ pub/sub
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

        # --- resource prep (extracted to core/run/prepare/resources.py) -----
        # Raises ValueError on schema-consistency failure — propagates to caller.
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
        prompt_bindings = prepared.prompt_bindings  # noqa: F841 — preserved for parity
        composed_result = prepared.composed_result
        _workspace_id = prepared.workspace_id

        # Resolve effective runner config and select backend adapter
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
            return self._fail_pre_run(agent, input_, workdir, session_id, str(exc))

        # Require a bound runner profile only when the caller did not
        # explicitly pick a backend (e.g. via the API ``backend=`` override
        # or programmatic ``execute(..., backend=...)`` from tests).
        if effective.backend is None and backend is None:
            error_msg = (
                f"agent {agent.id!r} has no runner profile bound. "
                "Assign a runner profile in the UI (Agents → Runner Profile)."
            )
            return self._fail_pre_run(agent, input_, workdir, session_id, error_msg)

        adapter, rendered = self._setup.select_backend(
            agent, workdir, backend, runner_config=effective, composed=composed
        )
        rendered, run_dir = self._setup.render_for_run(
            adapter, agent, workdir, rendered
        )

        # --- resolve MCP grants, then delegate file mutations to the backend.
        # Executor owns the store / capability checks; the backend's
        # ``post_render`` hook owns the on-disk MCP config format.
        _host_env_grants = self._snapshots.resolve_host_env_grants(_workspace_id)
        _agent_tool_grants = self._setup.resolve_agent_tool_grants(agent.id)
        self._setup.post_render(
            adapter,
            rendered,
            run_dir=run_dir,
            workdir=workdir,
            workspace_id=_workspace_id,
            agent_id=agent.id,
            host_env_grants=_host_env_grants,
            agent_tool_grants=_agent_tool_grants,
        )

        transcripts_dir = self.settings.data_dir / "transcripts"
        transcripts_dir.mkdir(parents=True, exist_ok=True)
        transcript_path = transcripts_dir / f"{uuid.uuid4().hex}.jsonl"
        run_id = self.store.create_run(
            agent_id=agent.id,
            input_=input_,
            workdir=str(workdir),
            transcript_path=str(transcript_path),
            session_id=session_id,
            config_digest=rendered.digest,
            runner_profile_id=effective.profile_id,
        )

        # Snapshot the resolved runner config — historical fact, never
        # updated. UI reads this so renaming/rebinding/deleting the
        # bound profile doesn't rewrite what the run page displays.
        self._snapshots.save_runner(
            run_id,
            build_runner_snapshot(
                self.store,
                effective=effective,
                rendered_model=rendered.model,
                backend_override=backend,
                runner_override=runner_override,
                runner_profile_id_param=runner_profile,
                runner_config_param=runner_config,
                timeout_override=timeout_seconds,
                agent=agent,
            ),
        )

        # Record the effective model immediately at run creation — before
        # the runner task starts — so every run has a model name in the
        # usage table regardless of backend, status, or whether the
        # runner ever emits a UsageEvent.
        if rendered.model:
            try:
                self.store.record_usage(run_id, {"model": rendered.model})
            except Exception:
                logger.exception("failed to pre-record model for run %s", run_id)

        # Persist conversation metadata from the backend adapter
        conv_format: str | None = getattr(adapter, "conversation_format", None)
        conv_uri: str | None = None
        if conv_format:
            conv_meth = getattr(adapter, "conversation_uri", None)
            if conv_meth is not None:
                conv_uri = conv_meth(
                    run_id=run_id, transcript_path=str(transcript_path)
                )
        self.store.set_run_conversation(run_id, conv_format, conv_uri)

        # Save composition metadata
        if composed_result is not None:
            snapshot = {
                "bundle_sha": composed_result.bundle_sha,
                "schema_sha": composed_result.schema_sha,
                "references": [
                    {"path": str(r) if isinstance(r, str) else r["path"]}
                    for r in (agent.composition.references if agent.composition else [])
                ],
            }
            self.store.save_run_composition(
                run_id=run_id,
                composition_snapshot=snapshot,
                rendered_prompt={
                    "system": composed_result.system,
                    "user": composed_result.user,
                    "schema": composed_result.schema,
                },
                variables=variables or {},
            )
        else:
            # Non-composition path (most agents): persist the final composed
            # system prompt — base + resource bindings + output-contract block —
            # so the run page can display exactly what the model received.
            _final_system = composed.system if composed.system is not None else (agent.prompt or "")
            _final_schema = composed.schema
            self.store.save_run_composition(
                run_id=run_id,
                composition_snapshot=None,
                rendered_prompt={
                    "system": _final_system,
                    "user": input_,
                    "schema": _final_schema
                    if isinstance(_final_schema, dict)
                    else None,
                },
                variables=variables or {},
            )

        # Persist resource + MCP snapshots (Plan 08 Phase 1+3)
        _mcp_snapshot = self._snapshots.build_mcp_snapshot(
            workspace_id=_workspace_id, host_env_grants=_host_env_grants
        )
        self._snapshots.save_resource_and_mcp(
            run_id,
            resource_snapshot=_resource_snapshot_entries,
            mcp_snapshot=_mcp_snapshot,
        )

        # Stamp run with current agent version
        self._stamp_run_agent_version(run_id, agent)

        # Embedded runner: caller will post snapshot later
        if runner_embedded:
            if variables:
                self.store.save_run_composition(
                    run_id=run_id,
                    composition_snapshot=None,
                    rendered_prompt=None,
                    variables=variables,
                )
            return run_id

        broadcaster = RunBroadcaster()
        self._broadcasters[run_id] = broadcaster
        try:
            frags = build_fragments(
                agent=agent,
                user_input=input_,
                project_root=self.settings.project_root,
                store=self.store,
                composed=composed,
            )
            self.store.save_run_prompt(run_id, fragments_to_json(frags))
        except Exception:
            pass
        task = asyncio.create_task(
            self._run(
                run_id,
                adapter,
                rendered,
                agent,
                input_,
                workdir,
                run_dir,
                transcript_path,
                broadcaster,
                effective=effective,
                composed=composed,
            )
        )
        self._tasks.add(task)
        self._run_tasks[run_id] = task

        def _on_task_done(t: asyncio.Task[None]) -> None:
            self._tasks.discard(t)
            self._run_tasks.pop(run_id, None)
            if not t.cancelled():
                exc = t.exception()
                if exc is not None:
                    logger.exception(
                        "run task crashed", exc_info=(type(exc), exc, exc.__traceback__)
                    )

        task.add_done_callback(_on_task_done)
        return run_id

    # ------------------------------------------------------------------ cancel
    async def cancel_run(self, run_id: str) -> bool:
        """Cancel an in-progress run.

        Marks the run as ``incomplete`` in the store first (so the
        executor's ``finally`` finish_run becomes a no-op — it only
        updates rows still in ``running``), emits a terminal ``DoneEvent``
        to any WS subscribers, then cancels the asyncio task driving the
        subprocess.

        Returns ``True`` if a running task was found and cancellation was
        initiated, ``False`` otherwise.
        """
        task = self._run_tasks.get(run_id)
        if task is None or task.done():
            return False

        error_msg = "cancelled by operator"
        try:
            self.store.finish_run(
                run_id,
                ok=False,
                error=error_msg,
                status=RunStatus.INCOMPLETE.value,
            )
        except Exception:
            logger.exception(
                "cancel_run: failed to persist incomplete status for %s", run_id
            )

        broadcaster = self._broadcasters.get(run_id)
        if broadcaster is not None:
            with contextlib.suppress(Exception):
                broadcaster.publish(
                    LogEvent(run_id=run_id, level="warn", message=error_msg)
                )
                broadcaster.publish(
                    DoneEvent(
                        run_id=run_id,
                        ok=False,
                        error=error_msg,
                        status=RunStatus.INCOMPLETE.value,
                    )
                )

        task.cancel()

        # Fire the webhook ourselves — the task's ``finally`` block
        # normally does this after finish_run, but we just short-circuited
        # finish_run (it's a no-op once the row is terminal) and the
        # cancellation may unwind before the finally schedules delivery.
        self._webhooks.deliver_for_cancel(run_id, broadcaster)

        return True

    # ------------------------------------------------------------------ run task
    async def _run(
        self,
        run_id: str,
        adapter,
        rendered,
        agent: AgentDef,
        input_: str,
        workdir: Path,
        run_dir: Path,
        transcript_path: Path,
        broadcaster: RunBroadcaster,
        effective=None,
        composed: Any | None = None,
    ) -> None:
        step_result = None
        try:
            step_result = await self._step_loop.run(
                run_id=run_id,
                adapter=adapter,
                rendered=rendered,
                agent=agent,
                input_=input_,
                workdir=workdir,
                transcript_path=transcript_path,
                broadcaster=broadcaster,
                effective=effective,
                composed=composed,
            )
        finally:
            self._finalizer.finalize(
                run_id=run_id,
                agent=agent,
                adapter=adapter,
                transcript_path=transcript_path,
                broadcaster=broadcaster,
                workdir=workdir,
                run_dir=run_dir,
                step_result=step_result,
            )

    # ------------------------------------------------------------------ misc helpers
    def _fail_pre_run(
        self,
        agent: AgentDef,
        input_: str,
        workdir: Path,
        session_id: str | None,
        error_msg: str,
    ) -> str:
        return _fail_pre_run_helper(
            self.store,
            self.settings,
            self._broadcasters,
            agent=agent,
            input_=input_,
            workdir=workdir,
            session_id=session_id,
            error_msg=error_msg,
        )

    def _inject_host_env_mcp(
        self,
        run_dir: Path,
        grants: dict,
        workspace_id: str,
        workdir: Path,
    ) -> None:
        """Back-compat wrapper around the post-render MCP helper.

        Production code goes through ``BackendAdapter.post_render``; this
        method survives because tests instantiate a ``MagicMock(spec=RunExecutor)``
        and call it as a bound method.
        """
        _inject_host_env_mcp_helper(
            run_dir=run_dir,
            grants=grants,
            workspace_id=workspace_id,
            workdir=workdir,
            db_path=self.settings.db_path,
        )

    def _inject_agent_tools_mcp(
        self,
        run_dir: Path,
        grants: set[str],
        agent_id: str,
        workdir: Path,
    ) -> None:
        """Back-compat wrapper around the post-render MCP helper."""
        _inject_agent_tools_mcp_helper(
            run_dir=run_dir,
            grants=grants,
            agent_id=agent_id,
            workdir=workdir,
            db_path=self.settings.db_path,
        )

    def _stamp_run_agent_version(self, run_id: str, agent: AgentDef) -> None:
        try:
            chosen = (
                self.store.get_active_version(agent.id)
                or self.store.latest_version(agent.id)
            )
            if chosen is not None:
                with self.store.engine.begin() as conn:
                    conn.execute(
                        _runs_table.update()
                        .where(_runs_table.c.id == run_id)
                        .values(agent_version_id=chosen["id"])
                    )
        except Exception:
            logger.exception("failed to stamp agent version for run %s", run_id)


__all__ = [
    "NoBackendAvailable",
    "RunBroadcaster",
    "RunExecutor",
    "_adapter_run_into_session",
]
