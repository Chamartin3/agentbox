"""End-to-end test fixtures.

Tests under ``tests/e2e/`` exercise the full stack with real backends,
live network connections, and persistent infrastructure. Everything
here is auto-marked ``e2e``, which the default ``addopts`` deselects;
opt in with ``-m e2e``. Some tests carry additional markers with their
own infra needs (e.g. ``live_ollama``).
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import agentbox.api.deps as deps
import pytest
from agentbox.api.app import create_app
from fastapi.testclient import TestClient


# --------------------------------------------------------------------------- #
# Auto-mark everything under tests/e2e/ as ``e2e`` (deselected by default)
# --------------------------------------------------------------------------- #


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    for item in items:
        if "/tests/e2e/" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)


# --------------------------------------------------------------------------- #
# Infra checks
# --------------------------------------------------------------------------- #


def _check_backend_binary(name: str) -> bool:
    return shutil.which(name) is not None


# --------------------------------------------------------------------------- #
# Data-dir isolation (same as integration, kept here for standalone e2e runs)
# --------------------------------------------------------------------------- #


@pytest.fixture
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``AGENTBOX_DATA_DIR`` at a per-test tmp dir."""
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_ROOT_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_SKIP_DEFAULT_PROFILES", "1")

    _reset_deps_caches()
    return tmp_path


@pytest.fixture
def client(isolated_data_dir: Path) -> Iterator[Any]:
    """FastAPI TestClient with an isolated data dir."""
    _reset_deps_caches()

    with TestClient(create_app()) as c:
        yield c

    _reset_deps_caches()


# Reset every lru_cache in ``api.deps`` plus the shared ``get_database`` pool so
# a prior test never leaks a service/Database bound to its own data dir. Named
# with a leading underscore and NOT a fixture — called from the fixtures above.
def _reset_deps_caches() -> None:
    from agentbox.core.db.database import get_database

    for _name in dir(deps):
        _fn = getattr(deps, _name)
        if hasattr(_fn, "cache_clear"):
            _fn.cache_clear()
    get_database.cache_clear()


# --------------------------------------------------------------------------- #
# Live-backend skip helpers (use in individual test decorators)
# --------------------------------------------------------------------------- #


def backend_required(name: str) -> pytest.MarkDecorator:
    return pytest.mark.skipif(
        not _check_backend_binary(name),
        reason=f"{name} not on PATH",
    )
