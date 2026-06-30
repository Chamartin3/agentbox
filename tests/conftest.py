"""Shared fixtures for the agentbox test suite.

Conventions:

- ``tests/unit/`` — auto-tagged ``unit``. Must not touch the database,
  network, or subprocess runners. Uses mocks exclusively.
- ``tests/integration/`` — auto-tagged ``integration``. Gets a real
  SQLite SessionStore and full FastAPI TestClient.
- ``tests/e2e/`` — auto-tagged ``e2e``. Full-stack tests with real
  backends and infrastructure. Conditionally skipped when infra is absent.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import agentbox.api.deps as deps
import pytest
from agentbox.api.app import create_app
from agentbox.core.db import SessionStore
from agentbox.core.db.database import Database
from fastapi.testclient import TestClient


# --------------------------------------------------------------------------- #
# Marker auto-tagging by directory
# --------------------------------------------------------------------------- #


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    for item in items:
        path = str(item.fspath)
        if "/tests/unit/" in path:
            item.add_marker(pytest.mark.unit)
        elif "/tests/integration/" in path:
            item.add_marker(pytest.mark.integration)
        elif "/tests/e2e/" in path:
            item.add_marker(pytest.mark.e2e)


# --------------------------------------------------------------------------- #
# Data-dir isolation
# --------------------------------------------------------------------------- #


@pytest.fixture
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``AGENTBOX_DATA_DIR`` at a per-test tmp dir."""
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_SKIP_DEFAULT_PROFILES", "1")
    manifest = tmp_path / "manifest.toml"
    manifest.write_text("# test manifest\n")
    monkeypatch.setenv("AGENTBOX_MANIFEST", str(manifest))

    for fn in (
        deps.get_settings,
        deps.get_store,
        deps.get_executor,
        deps.get_mcp_registry,
    ):
        fn.cache_clear()
    return tmp_path


# --------------------------------------------------------------------------- #
# Store + API client
# --------------------------------------------------------------------------- #


@pytest.fixture
def session_store(tmp_path: Path):  # type: ignore[no-untyped-def]
    """Fresh on-disk SessionStore (sqlite) under ``tmp_path``."""
    return SessionStore(tmp_path / "agentbox.sqlite")


@pytest.fixture
def db(tmp_path: Path):  # type: ignore[no-untyped-def]
    """Fresh on-disk Database (sqlite) under ``tmp_path``."""
    return Database(tmp_path / "agentbox.sqlite")


@pytest.fixture
def client(isolated_data_dir: Path) -> Iterator[Any]:
    """FastAPI TestClient with an isolated data dir."""
    for fn in (
        deps.get_settings,
        deps.get_store,
        deps.get_executor,
        deps.get_mcp_registry,
    ):
        fn.cache_clear()

    with TestClient(create_app()) as c:
        yield c

    for fn in (
        deps.get_settings,
        deps.get_store,
        deps.get_executor,
        deps.get_mcp_registry,
    ):
        fn.cache_clear()


# --------------------------------------------------------------------------- #
# Belt-and-braces: never inherit a stray AGENTBOX_DATA_DIR from the shell
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _scrub_agentbox_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("AGENTBOX_") and key != "AGENTBOX_DEBUG":
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AGENTBOX_IMPORT_ON_START", "1")


@pytest.fixture(autouse=True)
def _default_agentbox_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _scrub_agentbox_env: None
) -> None:
    """Point ``AGENTBOX_DATA_DIR`` at the per-test tmp dir (after the scrub).

    Self-wiring services (``ExecutionService()``/``EvaluationService()``/…) resolve
    their Database from ``load_settings().db_path`` = ``<tmp>/agentbox.sqlite``,
    which is the same db the ``store``/``session_store``/``db`` fixtures build.
    Tests that set their own ``AGENTBOX_DATA_DIR`` override this.
    """
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
