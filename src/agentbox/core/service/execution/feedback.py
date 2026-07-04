"""Run comments service."""

from __future__ import annotations

from agentbox.core.service.execution.service import ExecutionService
from agentbox.core.service.execution.types import RunNotFound


def _svc() -> ExecutionService:
    return ExecutionService()


def list_comments(run_id: str, *, store: object | None = None) -> dict:
    svc = _svc()
    if svc.get_run(run_id) is None:
        raise RunNotFound(run_id)
    return {"run_id": run_id, "comments": svc.list_run_comments(run_id)}


def add_comment(
    run_id: str, *, store: object | None = None, author: str, body: str
) -> dict:
    svc = _svc()
    if svc.get_run(run_id) is None:
        raise RunNotFound(run_id)
    return svc.add_run_comment(run_id, author, body)
