"""Integration tests for ``core.service.lifecycle.run_startup_tasks``.

The orchestrator must be safe to call on a fresh DB, idempotent across
repeated calls, and tolerant of missing manifests. These tests pin the
contract the FastAPI startup hook depends on.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from agentbox.core.config import load_settings
from agentbox.core.db import SessionStore
from agentbox.core.service.lifecycle import (
    StartupReport,
    run_startup_tasks,
)


@pytest.fixture
def lifecycle_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[SessionStore, object]:
    """Real SessionStore + Settings pointed at an isolated tmp dir."""
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_SKIP_DEFAULT_PROFILES", "1")
    monkeypatch.setenv("AGENTBOX_SKIP_RESOURCE_IMPORT", "1")
    settings = load_settings()
    store = SessionStore(tmp_path / "db.sqlite")
    return store, settings


def test_run_startup_tasks_on_empty_store_returns_clean_report(
    lifecycle_env: tuple[SessionStore, object],
) -> None:
    # Arrange
    store, settings = lifecycle_env

    # Act
    report = run_startup_tasks(store, settings, manifest=None)

    # Assert
    assert isinstance(report, StartupReport)
    assert report.errors == []
    assert report.tools_discovered is True
    assert report.runner_profiles_seeded == 0
    assert report.resources_created == 0


def test_run_startup_tasks_is_idempotent(
    lifecycle_env: tuple[SessionStore, object],
) -> None:
    # Arrange
    store, settings = lifecycle_env

    # Act
    first = run_startup_tasks(store, settings, manifest=None)
    second = run_startup_tasks(store, settings, manifest=None)

    # Assert — second pass must not raise and must not double-count
    # work the first pass already completed.
    assert first.errors == []
    assert second.errors == []
    assert second.runner_profiles_seeded == 0
    assert second.resources_created == 0


def test_run_startup_tasks_handles_seed_profiles_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — flip the skip flag off so the seed runs.
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_SKIP_RESOURCE_IMPORT", "1")
    monkeypatch.delenv("AGENTBOX_SKIP_DEFAULT_PROFILES", raising=False)
    settings = load_settings()
    store = SessionStore(tmp_path / "db.sqlite")

    # Act
    report = run_startup_tasks(store, settings, manifest=None)

    # Assert — at least one default profile was seeded.
    assert report.errors == []
    assert report.runner_profiles_seeded >= 1

    # Second pass must seed nothing (idempotent).
    second = run_startup_tasks(store, settings, manifest=None)
    assert second.runner_profiles_seeded == 0
