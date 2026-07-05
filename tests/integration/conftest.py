"""Integration-test fixtures.

All tests under ``tests/integration/`` get a real SQLite ``Database``
and a full FastAPI TestClient with an isolated data directory per test.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import agentbox.api.deps as api_deps
import agentbox.cli.shared.deps as cli_deps
import pytest
from agentbox.api.app import create_app
from fastapi.testclient import TestClient


# --------------------------------------------------------------------------- #
# Cache isolation
# --------------------------------------------------------------------------- #


def _reset_all_deps_caches() -> None:
    """Clear EVERY lru_cache in api.deps and cli.shared.deps plus the shared
    ``get_database`` pool. The service factories (get_agent_service, …) are
    ``@lru_cache`` and otherwise leak a service bound to a prior test's data
    dir, which makes seed-then-read tests flaky under the full suite."""
    from agentbox.core.db.database import get_database

    for deps in (api_deps, cli_deps):
        for name in dir(deps):
            fn = getattr(deps, name)
            if hasattr(fn, "cache_clear"):
                fn.cache_clear()
    get_database.cache_clear()


@pytest.fixture(autouse=True)
def _reset_agentbox_deps_caches() -> Iterator[None]:
    """Reset DI caches before AND after each integration test."""
    _reset_all_deps_caches()
    yield
    _reset_all_deps_caches()


# --------------------------------------------------------------------------- #
# Data-dir isolation
# --------------------------------------------------------------------------- #


@pytest.fixture
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``AGENTBOX_DATA_DIR`` at a per-test tmp dir.

    Creates a minimal ``manifest.toml`` and clears DI caches so
    ``create_app()`` uses the fresh data directory.
    """
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_ROOT_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_SKIP_DEFAULT_PROFILES", "1")

    for fn in (
        api_deps.get_settings,
        api_deps.get_executor,
        api_deps.get_mcp_registry,
    ):
        fn.cache_clear()
    return tmp_path


# --------------------------------------------------------------------------- #
# Store + API client
# --------------------------------------------------------------------------- #


@pytest.fixture
def client(isolated_data_dir: Path) -> Iterator[Any]:
    """FastAPI TestClient with an isolated data dir.

    Clears DI caches before and after each test so every ``client``
    sees the per-test ``AGENTBOX_DATA_DIR``.
    """
    for fn in (
        api_deps.get_settings,
        api_deps.get_executor,
        api_deps.get_mcp_registry,
    ):
        fn.cache_clear()

    with TestClient(create_app()) as c:
        yield c

    for fn in (
        api_deps.get_settings,
        api_deps.get_executor,
        api_deps.get_mcp_registry,
    ):
        fn.cache_clear()
