"""Unit-test fixtures.

All tests under ``tests/unit/`` must never touch the database, network,
or subprocess runners. These fixtures provide mock substitutes for every
integration dependency.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from agentbox.core.data import AgentDef, RunnerSpec


# --------------------------------------------------------------------------- #
# Core mocks
# --------------------------------------------------------------------------- #


@pytest.fixture
def mock_store() -> MagicMock:
    """MagicMock wrapping SessionStore — no SQLite, no filesystem."""
    return MagicMock()


@pytest.fixture
def mock_executor() -> MagicMock:
    """MagicMock wrapping RunExecutor."""
    return MagicMock()


# --------------------------------------------------------------------------- #
# Domain-object factories (pure dataclasses / pydantic models)
# --------------------------------------------------------------------------- #


@pytest.fixture
def make_agent_def():
    """Factory returning a minimal valid AgentDef for unit tests."""

    def _make(**overrides) -> AgentDef:
        defaults: dict = {
            "slug": "test-agent",
            "name": "Test Agent",
            "runner": RunnerSpec(kind="claude_code"),
        }
        defaults.update(overrides)
        return AgentDef(**defaults)

    return _make


@pytest.fixture
def make_runner_spec():
    """Factory returning a minimal valid RunnerSpec."""

    def _make(**overrides) -> RunnerSpec:
        defaults: dict = {"kind": "claude_code"}
        defaults.update(overrides)
        return RunnerSpec(**defaults)

    return _make
