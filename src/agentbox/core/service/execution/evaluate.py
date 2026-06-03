"""Run evaluation — comments."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agentbox.core.service.execution.types import RunNotFound

if TYPE_CHECKING:
    from agentbox.core.data import SessionStore


def list_comments(run_id: str, *, store: SessionStore) -> dict:
    if store.get_run(run_id) is None:
        raise RunNotFound(run_id)
    return {"run_id": run_id, "comments": store.list_run_comments(run_id)}


def add_comment(
    run_id: str, *, store: SessionStore, author: str, body: str
) -> dict:
    if store.get_run(run_id) is None:
        raise RunNotFound(run_id)
    return store.add_run_comment(run_id, author, body)
