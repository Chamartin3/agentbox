"""Inner run loop — extracted from RunExecutor._run()."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentbox.core.data import AgentDef
from agentbox.core.execution.orchestrate.broadcaster import RunBroadcaster
from agentbox.core.execution.orchestrate.finalizer import RunFinalizer
from agentbox.core.execution.orchestrate.steploop import RunStepLoop


async def _run(
    run_id: str,
    adapter: Any,
    rendered: Any,
    agent: AgentDef,
    input_: str,
    workdir: Path,
    run_dir: Path,
    transcript_path: Path,
    broadcaster: RunBroadcaster,
    step_loop: RunStepLoop,
    finalizer: RunFinalizer,
    effective: Any = None,
    composed: Any | None = None,
) -> None:
    step_result = None
    try:
        step_result = await step_loop.run(
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
        finalizer.finalize(
            run_id=run_id,
            agent=agent,
            adapter=adapter,
            transcript_path=transcript_path,
            broadcaster=broadcaster,
            workdir=workdir,
            run_dir=run_dir,
            step_result=step_result,
        )
