"""Run stream — transcript reader."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from agentbox.core.db import read_transcript
from agentbox.core.service.execution.service import ExecutionService
from agentbox.core.service.execution.types import RunNotFound

if TYPE_CHECKING:
    from agentbox.core.db import SessionStore


def _svc() -> ExecutionService:
    return ExecutionService()


def get_transcript(run_id: str, *, store: SessionStore) -> list[dict]:
    svc = _svc()
    rec = svc.get_run(run_id)
    if rec is None or not rec.transcript_path:
        raise RunNotFound(run_id)
    return read_transcript(Path(rec.transcript_path))
