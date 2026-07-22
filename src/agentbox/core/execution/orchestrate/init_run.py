"""Post-create-run row initialization, pre-run failure handling, and background
task launch — extracted from RunExecutor.execute()."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentbox.core.config import Settings
from agentbox.core.data.constants import LogLevel, RunStatus
from agentbox.core.data.events import DoneEvent, LogEvent
from agentbox.core.data import AgentDef
from agentbox.core.data.composition import ComposedPrompt
from agentbox.core.data._util import now_iso
from agentbox.core.db import (
    AgentVersionManager,
    RunManager,
    RunPromptManager,
    RunnerProfileManager,
    UsageManager,
)
from agentbox.core.execution.observability.stream.broadcaster import RunBroadcaster
from agentbox.core.execution.observability.snapshot import (
    SnapshotWriter,
    build_runner_snapshot,
    capture_fragments,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InitRunManagers:
    """Typed bundle of all managers needed by init_run and launch_background_task."""

    runs: RunManager
    agent_versions: AgentVersionManager
    usage: UsageManager
    run_prompts: RunPromptManager
    runner_profiles: RunnerProfileManager


# ---------------------------------------------------------------------------
# Pre-run failure helper (previously in pre_run.py)
# ---------------------------------------------------------------------------


def fail_pre_run(
    runs: RunManager,
    settings: Settings,
    broadcasters: dict[str, RunBroadcaster],
    *,
    agent: AgentDef,
    input_: str,
    workdir: Path,
    session_id: str | None,
    error_msg: str,
) -> str:
    """Create an error run record and broadcast failure before execution starts."""
    transcripts_dir = settings.data_dir / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = transcripts_dir / f"{uuid.uuid4().hex}.jsonl"
    run_id = uuid.uuid4().hex
    runs.create(
        id=run_id,
        agent_id=agent.id,
        input=input_,
        workdir=str(workdir),
        transcript_path=str(transcript_path),
        session_id=session_id,
        status=RunStatus.RUNNING.value,
        created_at=now_iso(),
    )
    runs.finish_full(run_id, ok=False, error=error_msg)
    broadcaster = RunBroadcaster()
    broadcasters[run_id] = broadcaster
    broadcaster.publish(
        LogEvent(run_id=run_id, level=LogLevel.ERROR, message=f"Error: {error_msg}")
    )
    broadcaster.publish(DoneEvent(run_id=run_id, ok=False, error=error_msg))
    broadcaster.close()
    return run_id


# ---------------------------------------------------------------------------
# Agent-version stamping helper (previously in pre_run.py)
# ---------------------------------------------------------------------------


def stamp_run_agent_version(
    runs: RunManager,
    agent_versions: AgentVersionManager,
    run_id: str,
    agent: AgentDef,
) -> None:
    """Stamp the run row with the active or latest agent version."""
    try:
        chosen = agent_versions.get_effective_active(agent.id)
        if chosen is not None:
            runs.set_agent_version(run_id, chosen["id"])
    except Exception:
        logger.exception("failed to stamp agent version for run %s", run_id)


# ---------------------------------------------------------------------------
# Run initialization
# ---------------------------------------------------------------------------


def init_run(
    *,
    run_id: str,
    agent: AgentDef,
    managers: InitRunManagers,
    settings: Any,
    adapter: Any,
    rendered: Any,
    composed: ComposedPrompt | None,
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
    """Initialize the run row after ``runs.create``."""
    _snapshots.save_runner(
        run_id,
        build_runner_snapshot(
            managers.runner_profiles,
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
            managers.usage.record(run_id, {"model": rendered.model})
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
    managers.runs.set_conversation(run_id, conv_format, conv_uri)

    if prepared_composed_result is not None:
        snapshot = {
            "bundle_sha": prepared_composed_result.bundle_sha,
            "schema_sha": prepared_composed_result.schema_sha,
            "references": [
                {"path": str(r) if isinstance(r, str) else (r["path"] if isinstance(r, dict) else getattr(r, "shared", str(r)))}
                for r in (agent.composition.references if agent.composition else [])
            ],
        }
        managers.runs.save_composition(
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
        _final_system = (
            composed.system_text if composed is not None and composed.system_text is not None
            else (agent.prompt or "")
        )
        _final_schema = composed.composed_schema if composed is not None else None
        managers.runs.save_composition(
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

    host_env_grants = _snapshots.resolve_host_env_grants(agent.id)
    _mcp_snapshot = _snapshots.build_mcp_snapshot(
        workspace_id=workspace_id, host_env_grants=host_env_grants
    )
    _snapshots.save_resource_and_mcp(
        run_id,
        resource_snapshot=resource_snapshot_entries,
        mcp_snapshot=_mcp_snapshot,
    )

    stamp_run_agent_version(managers.runs, managers.agent_versions, run_id, agent)


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
    managers: InitRunManagers,
    settings: Any,
    effective: Any,
    composed: ComposedPrompt | None,
    step_loop: Any,
    finalizer: Any,
    _run_loop: Any,
    broadcasters: dict[str, RunBroadcaster],
    tasks: set,
    run_tasks: dict[str, asyncio.Task],
    dispose_workdir: bool = False,
) -> str:
    """Create broadcaster, capture prompt fragments, and launch the run task."""
    broadcaster = RunBroadcaster()
    broadcasters[run_id] = broadcaster
    try:
        frags_json = capture_fragments(
            agent=agent,
            user_input=input_,
            project_root=settings.project_root,
            composed=composed,
            backend=getattr(effective, "backend", None),
        )
        managers.run_prompts.save(run_id, frags_json)
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
            dispose_workdir=dispose_workdir,
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
