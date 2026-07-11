"""Minimal host contract tests.

Verify that agentbox can start and serve requests when the manifest mount
is absent — DB is the source of truth.
"""

from __future__ import annotations

import warnings
from collections.abc import AsyncIterator
from pathlib import Path

import agentbox.core.engines.backends.registry as _plugins
import pytest
from agentbox.core.config import SETTINGS
from agentbox.core.data.events import DoneEvent, RunEvent
from agentbox.core.data import AgentDef
from agentbox.core.engines.backends.base import BackendAdapter
from agentbox.core.data import RenderedConfig
from agentbox.core.service.agents.service import AgentService
from fastapi.testclient import TestClient


def _register_noop_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inject a noop BackendAdapter into the plugins registry under 'claude_code'.

    Uses monkeypatch.setitem so the global registry is restored after the test —
    otherwise the swap leaks into later tests (e.g. list_recipes() would drop
    claude_code because _NoopBackend has no recipe.yaml).
    """

    class _NoopBackend(BackendAdapter):
        name = "claude_code"

        def render(
            self, agent: object, workdir: Path, *args: object, **kw: object
        ) -> RenderedConfig:
            return RenderedConfig(argv=["true"], env={}, cwd=Path("."))

        async def run(
            self, rendered: RenderedConfig, input: str, run_id: str
        ) -> AsyncIterator[RunEvent]:
            yield DoneEvent(run_id=run_id, ok=True)

    registry = _plugins.backends()
    monkeypatch.setitem(registry, "claude_code", _NoopBackend)


def test_health_with_minimal_mounts(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200


def test_agents_list_empty_on_clean_db(client: TestClient) -> None:
    """``/api/agents`` returns ``[]`` when no agent has been registered in the DB."""
    resp = client.get("/api/agents")
    assert resp.status_code == 200
    assert resp.json() == []


def test_optional_mounts_absent_from_settings(
    isolated_data_dir: Path,
) -> None:
    """With only AGENTBOX_MANIFEST set, all optional dirs resolve to None."""
    assert SETTINGS.agents_dir is None
    assert SETTINGS.prompts_dir is None
    assert SETTINGS.skills_dir is None
    assert SETTINGS.outputs_dir is None


def test_workspaces_root_absent_does_not_crash(
    isolated_data_dir: Path, client: TestClient
) -> None:
    assert not SETTINGS.workspaces_root.exists()

    resp = client.get("/api/agents")
    assert resp.status_code == 200


def test_run_with_db_seeded_noop_agent(
    isolated_data_dir: Path, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /api/runs completes against an agent stored only in the DB."""
    _register_noop_backend(monkeypatch)

    agent = AgentDef.model_validate(
        {
            "id": "noop",
            "description": "noop",
            "session_mode": "headless",
            "headless": True,
            "runner": {"kind": "claude_code", "timeout_seconds": 5},
        }
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=UserWarning)
        config_json = agent.model_dump_json()

    row = AgentService().create_version(
        agent_id="noop",
        source_path="",
        source_format="db_only",
        content_snapshot=config_json,
        prompt_snapshot="",
        content_hash="x",
        config_json=config_json,
        prompt_content="",
        source="manifest",
    )
    AgentService().activate_version("noop", row["id"])

    resp = client.post("/api/runs", json={"agent": "noop", "input": "ping"})
    assert resp.status_code in (200, 201, 202), resp.text
    assert "run_id" in resp.json()
