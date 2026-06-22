"""End-to-end test fixtures.

Tests under ``tests/e2e/`` exercise the full stack with real backends,
live network connections, and persistent infrastructure. Everything
here is auto-marked ``e2e``, which the default ``addopts`` deselects;
opt in with ``-m e2e``. Some tests carry additional markers with their
own infra needs (e.g. ``live_ollama``).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest


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
    import shutil

    return shutil.which(name) is not None


# --------------------------------------------------------------------------- #
# Data-dir isolation (same as integration, kept here for standalone e2e runs)
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
    """FastAPI TestClient with an isolated data dir."""
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


# --------------------------------------------------------------------------- #
# Live-backend skip helpers (use in individual test decorators)
# --------------------------------------------------------------------------- #


def backend_required(name: str) -> pytest.MarkDecorator:
    return pytest.mark.skipif(
        not _check_backend_binary(name),
        reason=f"{name} not on PATH",
    )
