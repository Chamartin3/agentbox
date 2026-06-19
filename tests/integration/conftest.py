"""Integration-test fixtures.

All tests under ``tests/integration/`` get a real SQLite SessionStore
and a full FastAPI TestClient with an isolated data directory per test.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest


# --------------------------------------------------------------------------- #
# Cache isolation
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _reset_agentbox_deps_caches() -> Iterator[None]:
    """Clear every lru_cache in agentbox.api.deps and agentbox.cli._deps
    before AND after each integration test so cached singletons don't leak."""
    import agentbox.api.deps as api_deps
    import agentbox.cli._deps as cli_deps

    for deps in (api_deps, cli_deps):
        for fn in (
            deps.get_settings,
            deps.get_store,
            deps.get_executor,
            deps.get_mcp_registry,
        ):
            fn.cache_clear()
    yield
    for deps in (api_deps, cli_deps):
        for fn in (
            deps.get_settings,
            deps.get_store,
            deps.get_executor,
            deps.get_mcp_registry,
        ):
            fn.cache_clear()


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
    monkeypatch.setenv("AGENTBOX_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_SKIP_DEFAULT_PROFILES", "1")
    manifest = tmp_path / "manifest.toml"
    manifest.write_text("# test manifest\n")
    monkeypatch.setenv("AGENTBOX_MANIFEST", str(manifest))

    try:
        import agentbox.api.deps as _deps

        for fn in (
            _deps.get_settings,
            _deps.get_store,
            _deps.get_executor,
            _deps.get_mcp_registry,
        ):
            fn.cache_clear()
    except (ImportError, AttributeError):
        pass
    return tmp_path


# --------------------------------------------------------------------------- #
# Store + API client
# --------------------------------------------------------------------------- #


@pytest.fixture
def session_store(tmp_path: Path):  # type: ignore[no-untyped-def]
    """Fresh on-disk SessionStore (sqlite) under ``tmp_path``."""
    from agentbox.core.db import SessionStore

    return SessionStore(tmp_path / "db.sqlite")


@pytest.fixture
def db(tmp_path: Path):  # type: ignore[no-untyped-def]
    """Fresh on-disk Database (sqlite) under ``tmp_path``."""
    from agentbox.core.db import Database

    return Database(tmp_path / "db.sqlite")


@pytest.fixture
def client(isolated_data_dir: Path) -> Iterator[Any]:
    """FastAPI TestClient with an isolated data dir.

    Clears DI caches before and after each test so every ``client``
    sees the per-test ``AGENTBOX_DATA_DIR``.
    """
    import agentbox.api.deps as deps
    from agentbox.api.app import create_app
    from fastapi.testclient import TestClient

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
