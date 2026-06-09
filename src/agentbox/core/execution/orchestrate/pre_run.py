"""Pre-run helpers — extracted from RunExecutor and RunSetup."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from agentbox.config import Settings
from agentbox.core.data import AgentDef, DoneEvent, LogEvent, RunSetupStore
from agentbox.core.data import runs as _runs_table
from agentbox.core.execution.orchestrate.broadcaster import RunBroadcaster

logger = logging.getLogger(__name__)


def fail_pre_run(
    store: RunSetupStore,
    settings: Settings,
    broadcasters: dict[str, RunBroadcaster],
    *,
    agent: AgentDef,
    input_: str,
    workdir: Path,
    session_id: str | None,
    error_msg: str,
) -> str:
    """Create an error run record and broadcast failure before execution starts.

    Used when something during setup (workdir, profile resolution, missing
    backend) makes it impossible to launch the run task. We still create a
    row so the operator can see the failure in the UI / API.
    """
    transcripts_dir = settings.data_dir / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = transcripts_dir / f"{uuid.uuid4().hex}.jsonl"
    run_id = store.create_run(
        agent_id=agent.id,
        input_=input_,
        workdir=str(workdir),
        transcript_path=str(transcript_path),
        session_id=session_id,
    )
    store.finish_run(run_id, ok=False, error=error_msg)
    broadcaster = RunBroadcaster()
    broadcasters[run_id] = broadcaster
    broadcaster.publish(
        LogEvent(run_id=run_id, level="error", message=f"Error: {error_msg}")
    )
    broadcaster.publish(DoneEvent(run_id=run_id, ok=False, error=error_msg))
    broadcaster.close()
    return run_id


def stamp_run_agent_version(
    store: Any,
    run_id: str,
    agent: AgentDef,
) -> None:
    """Stamp the run row with the active or latest agent version."""
    try:
        chosen = (
            store.get_active_version(agent.id)
            or store.latest_version(agent.id)
        )
        if chosen is not None:
            with store.engine.begin() as conn:
                conn.execute(
                    _runs_table.update()
                    .where(_runs_table.c.id == run_id)
                    .values(agent_version_id=chosen["id"])
                )
    except Exception:
        logger.exception("failed to stamp agent version for run %s", run_id)
