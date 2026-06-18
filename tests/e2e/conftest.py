"""End-to-end test fixtures.

Tests under ``tests/e2e/`` exercise the full stack with real backends,
live network connections, and persistent infrastructure. They are
conditionally skipped when the required environment is not available.

Set ``AGENTBOX_E2E=1`` to opt in to the e2e suite. Individual tests
may impose additional requirements (e.g. ``OLLAMA_HOST``).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest


# --------------------------------------------------------------------------- #
# Conditional skip — entire e2e suite
# --------------------------------------------------------------------------- #


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item],
) -> None:
    if not os.environ.get("AGENTBOX_E2E"):
        skip_e2e = pytest.mark.skip(reason="AGENTBOX_E2E not set")
        for item in items:
            if "/tests/e2e/" in str(item.fspath):
                item.add_marker(skip_e2e)


# --------------------------------------------------------------------------- #
# Infra checks
# --------------------------------------------------------------------------- #


def _check_ollama() -> bool:
    return bool(os.environ.get("OLLAMA_HOST"))


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
            _deps.get_loader,
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
        deps.get_loader,
        deps.get_executor,
        deps.get_mcp_registry,
    ):
        fn.cache_clear()

    with TestClient(create_app()) as c:
        yield c

    for fn in (
        deps.get_settings,
        deps.get_store,
        deps.get_loader,
        deps.get_executor,
        deps.get_mcp_registry,
    ):
        fn.cache_clear()


# --------------------------------------------------------------------------- #
# Live-backend skip helpers (use in individual test decorators)
# --------------------------------------------------------------------------- #


ollama_required = pytest.mark.skipif(
    not _check_ollama(),
    reason="OLLAMA_HOST not set",
)


def backend_required(name: str) -> pytest.MarkDecorator:
    return pytest.mark.skipif(
        not _check_backend_binary(name),
        reason=f"{name} not on PATH",
    )
