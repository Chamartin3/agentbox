"""Minimal host contract tests.

Verify that agentbox can start and serve requests when the manifest mount
is absent — DB is the source of truth.
"""

from __future__ import annotations

import warnings
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import agentbox.core.engines.backends.registry as _plugins
from agentbox.api.deps import get_store
from agentbox.core.config import SETTINGS
from agentbox.core.events import DoneEvent, RunEvent
from agentbox.core.data import AgentDef
from agentbox.core.engines.contracts.base import RenderedConfig


def _register_noop_backend(monkeypatch: Any) -> None:
    """Inject a noop BackendAdapter into the plugins registry under 'claude_code'.

    Uses monkeypatch.setitem so the global registry is restored after the test —
    otherwise the swap leaks into later tests (e.g. list_recipes() would drop
    claude_code because _NoopBackend has no recipe.yaml).
    """

    class _NoopBackend:
        name = "claude_code"

        def render(
            self,
            agent: Any,
            workdir: Path,
            mcp_tools: Any = None,
            creds: Any = None,
            runner_config: Any = None,
        ) -> RenderedConfig:
            return RenderedConfig(argv=["true"], env={}, cwd=Path("."))

        async def run(  # type: ignore[override]
            self, rendered: RenderedConfig, input: str, run_id: str
        ) -> AsyncIterator[RunEvent]:
            yield DoneEvent(run_id=run_id, ok=True, output="noop done")

    _plugins.backends()
    monkeypatch.setitem(_plugins._BACKEND_CLASSES, "claude_code", _NoopBackend)  # type: ignore[arg-type]


def test_health_with_minimal_mounts(client: Any) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200


def test_agents_list_empty_on_clean_db(client: Any) -> None:
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
    isolated_data_dir: Path, client: Any
) -> None:
    assert not SETTINGS.workspaces_root.exists()

    resp = client.get("/api/agents")
    assert resp.status_code == 200


def test_run_with_db_seeded_noop_agent(
    isolated_data_dir: Path, client: Any, monkeypatch: Any
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

    store = get_store()
    row = store.create_version(
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
    store.activate_version("noop", row["id"])

    resp = client.post("/api/runs", json={"agent": "noop", "input": "ping"})
    assert resp.status_code in (200, 201, 202), resp.text
    assert "run_id" in resp.json()
