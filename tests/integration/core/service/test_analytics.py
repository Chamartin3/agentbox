"""Tests for ``core.service.execution.feedback`` — enrichment + rollups over run rows."""

from __future__ import annotations

from pathlib import Path

import pytest
from agentbox.core.service import SessionStore
from agentbox.core.service.execution.feedback import (
    activity_summary,
    add_comment,
    aggregate_usage,
    distinct_executors,
    enrich_recent_runs,
    list_comments,
    since_iso,
    success_rate,
    summary,
)


@pytest.fixture
def store(tmp_path: Path) -> SessionStore:
    return SessionStore(tmp_path / "agentbox.sqlite")


# ── since_iso ───────────────────────────────────────────────────────────


def test_since_iso_returns_iso_string() -> None:
    result = since_iso("7d")
    assert result.endswith("+00:00")
    assert "T" in result


def test_since_iso_all_ranges_are_valid() -> None:
    for r in ("7d", "30d", "90d"):
        assert "T" in since_iso(r)


# ── enrich_recent_runs ──────────────────────────────────────────────────


def test_enrich_recent_runs_empty_store(store: SessionStore) -> None:
    result = enrich_recent_runs(store, range_="30d")
    assert result == {"results": [], "total": 0}


def test_enrich_recent_runs_shapes_correctly(store: SessionStore) -> None:
    """Verify envelope shape is correct even with empty data."""
    result = enrich_recent_runs(store, range_="7d")
    assert "results" in result
    assert "total" in result
    assert isinstance(result["results"], list)


# ── summary ─────────────────────────────────────────────────────────────


def test_summary_empty_store(store: SessionStore) -> None:
    result = summary(store, range_="30d")
    assert isinstance(result, dict)


def test_summary_shapes_correctly(store: SessionStore) -> None:
    """Verify summary returns a dict-shaped response."""
    result = summary(store, range_="7d")
    assert isinstance(result, dict)


# ── facade contract ─────────────────────────────────────────────────────


def test_feedback_facade_exports_required_functions() -> None:
    assert callable(activity_summary)
    assert callable(add_comment)
    assert callable(aggregate_usage)
    assert callable(distinct_executors)
    assert callable(enrich_recent_runs)
    assert callable(list_comments)
    assert callable(success_rate)
    assert callable(summary)


def test_old_feedback_package_is_gone() -> None:
    parts = ["agentbox", "core", "service", "feedback"]
    with pytest.raises(ImportError):
        __import__(".".join(parts))
