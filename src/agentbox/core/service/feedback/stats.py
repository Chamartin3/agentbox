"""Feedback statistics service helpers."""

from __future__ import annotations

from agentbox.core.data import SessionStore


def aggregate_usage(*, store: SessionStore) -> dict:
    """Total tokens + cost across all runs."""
    return store.aggregate_usage()


def activity_summary(*, store: SessionStore, since: str, agent_id: str | None = None) -> dict:
    """Roll up runs since ``since`` (ISO-8601) into totals + breakdowns."""
    return store.activity_summary(since, agent=agent_id)
