"""Tests for ``EvaluationService`` — run/agent analytics (plan 093).

Migrated from ``core.service.execution.feedback``; analytics now lives on
``EvaluationService``.  Tests that need a DB use ``isolated_data_dir`` so
``EvaluationService()`` resolves to an isolated per-test SQLite file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agentbox.core.service.evaluation import since_iso
from agentbox.core.service.evaluation.service import EvaluationService
from agentbox.core.service.execution import ExecutionService


# ── since_iso ───────────────────────────────────────────────────────────


def test_since_iso_returns_iso_string() -> None:
    result = since_iso("7d")
    assert result.endswith("+00:00")
    assert "T" in result


def test_since_iso_all_ranges_are_valid() -> None:
    for r in ("7d", "30d", "90d"):
        assert "T" in since_iso(r)


# ── EvaluationService — empty-store behaviour ───────────────────────────


def test_list_runs_enriched_empty_store(isolated_data_dir: Path) -> None:
    result = EvaluationService().list_runs_enriched(range_="30d")
    assert result == {"results": [], "total": 0}


def test_list_runs_enriched_shapes_correctly(isolated_data_dir: Path) -> None:
    """Verify envelope shape is correct even with empty data."""
    result = EvaluationService().list_runs_enriched(range_="7d")
    assert "results" in result
    assert "total" in result
    assert isinstance(result["results"], list)


def test_activity_summary_empty_store(isolated_data_dir: Path) -> None:
    result = EvaluationService().activity_summary(since_iso("30d"))
    assert isinstance(result, dict)


def test_activity_summary_shapes_correctly(isolated_data_dir: Path) -> None:
    """Verify activity_summary returns a dict-shaped response."""
    result = EvaluationService().activity_summary(since_iso("7d"))
    assert isinstance(result, dict)


def test_aggregate_usage_empty_store(isolated_data_dir: Path) -> None:
    result = EvaluationService().aggregate_usage()
    assert isinstance(result, dict)


def test_distinct_executors_empty_store(isolated_data_dir: Path) -> None:
    result = EvaluationService().distinct_executors()
    assert isinstance(result, list)


# ── facade contract ─────────────────────────────────────────────────────


def test_evaluation_service_has_required_methods() -> None:
    assert callable(EvaluationService.activity_summary)
    assert callable(EvaluationService.aggregate_usage)
    assert callable(EvaluationService.distinct_executors)
    assert callable(EvaluationService.list_runs_enriched)
    assert callable(EvaluationService.list_runs_paged)
    assert callable(EvaluationService.list_runs_rich)
    assert callable(EvaluationService.stats_for_filters)
    assert callable(EvaluationService.runner_profile_stats)
    assert callable(EvaluationService.list_runner_profile_stats)


def test_execution_service_has_comment_methods() -> None:
    """Comments (add/list) live on ExecutionService, not evaluation."""
    assert callable(ExecutionService.add_comment)
    assert callable(ExecutionService.list_comments)


def test_old_feedback_package_is_gone() -> None:
    parts = ["agentbox", "core", "service", "feedback"]
    with pytest.raises(ImportError):
        __import__(".".join(parts))
