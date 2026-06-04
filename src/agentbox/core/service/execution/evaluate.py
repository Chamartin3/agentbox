"""Run evaluation — comments, usage, and activity stats."""

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


def aggregate_usage(*, store: SessionStore) -> dict:
    """Total tokens + cost across all runs."""
    return store.aggregate_usage()


def activity_summary(*, store: SessionStore, since: str, agent_id: str | None = None) -> dict:
    """Roll up runs since ``since`` (ISO-8601) into totals + breakdowns."""
    return store.activity_summary(since, agent=agent_id)


def distinct_executors(*, store: SessionStore) -> list[str]:
    """Distinct executor/model names across all recorded runs."""
    return store.distinct_executors()
