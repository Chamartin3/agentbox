"""Shared fixtures for the agentbox test suite.

Conventions:

- ``tests/unit/`` — auto-tagged ``unit``. Must not touch the database,
  network, or subprocess runners. Uses mocks exclusively.
- ``tests/integration/`` — auto-tagged ``integration``. Gets a real
  SQLite ``Database`` and full FastAPI TestClient.
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
from agentbox.core.db import (
    AgentManager,
    AgentToolGrantManager,
    AgentVersionManager,
    McpToolDiscoveryCacheManager,
    PromptVersionManager,
    ResourceManager,
    RunManager,
    RunnerProfileManager,
    SessionManager,
    SharedResourceManager,
    UsageManager,
    WorkspaceManager,
    WorkspaceSubagentManager,
)
from agentbox.core.db.database import Database
from agentbox.core.service import (
    AgentService,
    EvaluationService,
    ExecutionService,
    ResourceService,
    SystemService,
    WorkspaceService,
)
from agentbox.core.service.engines import EngineService
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
    monkeypatch.setenv("AGENTBOX_ROOT_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_SKIP_DEFAULT_PROFILES", "1")

    for fn in (
        deps.get_settings,
        deps.get_executor,
        deps.get_mcp_registry,
    ):
        fn.cache_clear()
    return tmp_path


# --------------------------------------------------------------------------- #
# Store + API client
# --------------------------------------------------------------------------- #


@pytest.fixture
def db(tmp_path: Path) -> Database:
    """Fresh on-disk Database (sqlite) under ``tmp_path``."""
    return Database(tmp_path / "agentbox.sqlite")


# --------------------------------------------------------------------------- #
# Per-manager fixtures — inject the manager you need, not the whole Database.
# Each just projects an attribute off the ``db`` fixture so tests never import
# ``Database`` or construct it. Add more here as tests need them.
# --------------------------------------------------------------------------- #


@pytest.fixture
def runs(db: Database) -> RunManager:
    return db.runs


@pytest.fixture
def sessions(db: Database) -> SessionManager:
    return db.sessions


@pytest.fixture
def usage(db: Database) -> UsageManager:
    return db.usage


@pytest.fixture
def agents(db: Database) -> AgentManager:
    return db.agents


@pytest.fixture
def agent_versions(db: Database) -> AgentVersionManager:
    return db.agent_versions


@pytest.fixture
def prompt_versions(db: Database) -> PromptVersionManager:
    return db.prompt_versions


@pytest.fixture
def workspaces(db: Database) -> WorkspaceManager:
    return db.workspaces


@pytest.fixture
def resources(db: Database) -> ResourceManager:
    return db.resources


@pytest.fixture
def shared_resources(db: Database) -> SharedResourceManager:
    return db.shared_resources


@pytest.fixture
def runner_profiles(db: Database) -> RunnerProfileManager:
    return db.runner_profiles


@pytest.fixture
def workspace_subagents(db: Database) -> WorkspaceSubagentManager:
    return db.workspace_subagents


@pytest.fixture
def agent_tool_grants(db: Database) -> AgentToolGrantManager:
    return db.agent_tool_grants


@pytest.fixture
def mcp_tool_discovery_cache(db: Database) -> McpToolDiscoveryCacheManager:
    return db.mcp_tool_discovery_cache


# --------------------------------------------------------------------------- #
# Service fixtures — request these for service-level behavior instead of
# constructing ``AgentService()`` etc. inside the test. They self-wire from
# ``load_settings().db_path`` which (via the autouse ``AGENTBOX_DATA_DIR``
# override) is the SAME sqlite file the ``db``/manager fixtures use, so seeding
# through a manager fixture is visible to the service and vice-versa.
# --------------------------------------------------------------------------- #


@pytest.fixture
def agent_service(db: Database) -> AgentService:
    return AgentService()


@pytest.fixture
def workspace_service(db: Database) -> WorkspaceService:
    return WorkspaceService()


@pytest.fixture
def execution_service(db: Database) -> ExecutionService:
    return ExecutionService()


@pytest.fixture
def resource_service(db: Database) -> ResourceService:
    return ResourceService()


@pytest.fixture
def evaluation_service(db: Database) -> EvaluationService:
    return EvaluationService()


@pytest.fixture
def system_service(db: Database) -> SystemService:
    return SystemService()


@pytest.fixture
def engine_service(db: Database) -> EngineService:
    return EngineService()


@pytest.fixture
def client(isolated_data_dir: Path) -> Iterator[Any]:
    """FastAPI TestClient with an isolated data dir."""
    for fn in (
        deps.get_settings,
        deps.get_executor,
        deps.get_mcp_registry,
    ):
        fn.cache_clear()

    with TestClient(create_app()) as c:
        yield c

    for fn in (
        deps.get_settings,
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
