"""Shared fixtures for the agentbox test suite.

Conventions:

- Tests under ``tests/unit/`` are auto-tagged ``unit`` and must not touch
  the network, subprocess runners, or a real SessionStore on disk.
- Tests under ``tests/integration/`` are auto-tagged ``integration`` and
  get an isolated ``AGENTBOX_DATA_DIR`` per test via ``isolated_data_dir``.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

# --------------------------------------------------------------------------- #
# Marker auto-tagging by directory
# --------------------------------------------------------------------------- #


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    for item in items:
        path = str(item.fspath)
        if "/tests/unit/" in path:
            item.add_marker(pytest.mark.unit)
        elif "/tests/integration/" in path:
            item.add_marker(pytest.mark.integration)
        elif "/tests/mcp/" in path:
            # MCP grouping/manifest/client tests are unit-level (pure logic,
            # no network, no executor). Treat them as unit by default so
            # ``pytest -m unit`` runs the fast lane.
            item.add_marker(pytest.mark.unit)


# --------------------------------------------------------------------------- #
# Data-dir isolation
# --------------------------------------------------------------------------- #


@pytest.fixture
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``AGENTBOX_DATA_DIR`` at a per-test tmp dir.

    Reloads ``agentbox.config`` so the SETTINGS singleton picks up the
    new value. Use in any test that constructs ``SessionStore`` from
    ``settings.db_path`` or calls ``create_app()``.
    """
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_SKIP_DEFAULT_PROFILES", "1")
    manifest = tmp_path / "manifest.toml"
    manifest.write_text("# test manifest\n")
    monkeypatch.setenv("AGENTBOX_MANIFEST", str(manifest))

    # Clear lru_caches so the next call reads the new env vars instead of
    # returning stale singletons from a previous test. get_settings() now
    # calls load_settings() directly so no module reload is needed.
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


# --------------------------------------------------------------------------- #
# Store + API client
# --------------------------------------------------------------------------- #


@pytest.fixture
def session_store(tmp_path: Path):  # type: ignore[no-untyped-def]
    """Fresh on-disk SessionStore (sqlite) under ``tmp_path``."""
    from agentbox.core.data.store import SessionStore

    return SessionStore(tmp_path / "db.sqlite")


@pytest.fixture
def client(isolated_data_dir: Path) -> Iterator[Any]:
    """FastAPI TestClient with an isolated data dir.

    The DI helpers in ``agentbox.api.deps`` use ``@lru_cache`` so the
    first call's settings/store/executor would otherwise be pinned for
    the entire test session. Clear those caches per test so each
    ``client`` sees the per-test ``AGENTBOX_DATA_DIR``.
    """
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
# Belt-and-braces: never inherit a stray AGENTBOX_DATA_DIR from the shell
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _scrub_agentbox_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("AGENTBOX_") and key != "AGENTBOX_DEBUG":
            monkeypatch.delenv(key, raising=False)
    # Plan 18 gated startup_sweep behind an opt-in flag. Most existing
    # tests still rely on filesystem→DB auto-import to seed agents, so
    # enable it by default for the test suite. Tests that exercise the
    # gated-off behavior can monkeypatch.delenv this back out.
    monkeypatch.setenv("AGENTBOX_IMPORT_ON_START", "1")
