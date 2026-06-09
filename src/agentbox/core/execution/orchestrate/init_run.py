"""Post-create-run row initialization — extracted from RunExecutor.execute()."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from agentbox.core.agents import capture_fragments
from agentbox.core.data import AgentDef
from agentbox.core.execution.orchestrate.broadcaster import RunBroadcaster
from agentbox.core.execution.orchestrate.pre_run import stamp_run_agent_version
from agentbox.core.execution.orchestrate.snapshots import (
    SnapshotWriter,
    build_runner_snapshot,
)

logger = logging.getLogger(__name__)


def init_run(
    *,
    run_id: str,
    agent: AgentDef,
    store: Any,
    settings: Any,
    adapter: Any,
    rendered: Any,
    composed: Any,
    input_: Any,
    transcript_path: Path,
    _snapshots: SnapshotWriter,
    _setup: Any,
    effective: Any,
    backend_override: str | None,
    runner_override: str | None,
    runner_profile: str | None,
    runner_config: dict[str, Any] | None,
    timeout_override: int | None,
    workspace_id: str | None,
    resource_snapshot_entries: list | None,
    prepared_composed_result: Any,
    variables: dict[str, Any] | None,
) -> None:
    """Initialize the run row after ``store.create_run``."""
    _snapshots.save_runner(
        run_id,
        build_runner_snapshot(
            store,
            effective=effective,
            rendered_model=rendered.model,
            backend_override=backend_override,
            runner_override=runner_override,
            runner_profile_id_param=runner_profile,
            runner_config_param=runner_config,
            timeout_override=timeout_override,
            agent=agent,
        ),
    )

    if rendered.model:
        try:
            store.record_usage(run_id, {"model": rendered.model})
        except Exception:
            logger.exception("failed to pre-record model for run %s", run_id)

    conv_format: str | None = getattr(adapter, "conversation_format", None)
    conv_uri: str | None = None
    if conv_format:
        conv_meth = getattr(adapter, "conversation_uri", None)
        if conv_meth is not None:
            conv_uri = conv_meth(
                run_id=run_id, transcript_path=str(transcript_path)
            )
    store.set_run_conversation(run_id, conv_format, conv_uri)

    if prepared_composed_result is not None:
        snapshot = {
            "bundle_sha": prepared_composed_result.bundle_sha,
            "schema_sha": prepared_composed_result.schema_sha,
            "references": [
                {"path": str(r) if isinstance(r, str) else r["path"]}
                for r in (agent.composition.references if agent.composition else [])
            ],
        }
        store.save_run_composition(
            run_id=run_id,
            composition_snapshot=snapshot,
            rendered_prompt={
                "system": prepared_composed_result.system,
                "user": prepared_composed_result.user,
                "schema": prepared_composed_result.schema,
            },
            variables=variables or {},
        )
    else:
        _final_system = composed.system if composed.system is not None else (agent.prompt or "")
        _final_schema = composed.schema
        store.save_run_composition(
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

    host_env_grants = _snapshots.resolve_host_env_grants(workspace_id)
    _mcp_snapshot = _snapshots.build_mcp_snapshot(
        workspace_id=workspace_id, host_env_grants=host_env_grants
    )
    _snapshots.save_resource_and_mcp(
        run_id,
        resource_snapshot=resource_snapshot_entries,
        mcp_snapshot=_mcp_snapshot,
    )

    stamp_run_agent_version(store, run_id, agent)


def launch_background_task(
    *,
    run_id: str,
    adapter: Any,
    rendered: Any,
    agent: AgentDef,
    input_: str,
    workdir: Path,
    run_dir: Path,
    transcript_path: Path,
    store: Any,
    settings: Any,
    effective: Any,
    composed: Any,
    step_loop: Any,
    finalizer: Any,
    _run_loop: Any,
    broadcasters: dict[str, RunBroadcaster],
    tasks: set,
    run_tasks: dict[str, Any],
) -> str:
    """Create broadcaster, capture prompt fragments, and launch the run task."""
    broadcaster = RunBroadcaster()
    broadcasters[run_id] = broadcaster
    try:
        frags_json = capture_fragments(
            agent=agent,
            user_input=input_,
            project_root=settings.project_root,
            store=store,
            composed=composed,
        )
        store.save_run_prompt(run_id, frags_json)
    except Exception:
        pass

    task = asyncio.create_task(
        _run_loop(
            run_id,
            adapter,
            rendered,
            agent,
            input_,
            workdir,
            run_dir,
            transcript_path,
            broadcaster,
            step_loop,
            finalizer,
            effective=effective,
            composed=composed,
        )
    )
    tasks.add(task)
    run_tasks[run_id] = task

    def _on_task_done(t: asyncio.Task[None]) -> None:
        tasks.discard(t)
        run_tasks.pop(run_id, None)
        if not t.cancelled():
            exc = t.exception()
            if exc is not None:
                logger.exception(
                    "run task crashed", exc_info=(type(exc), exc, exc.__traceback__)
                )

    task.add_done_callback(_on_task_done)
    return run_id
