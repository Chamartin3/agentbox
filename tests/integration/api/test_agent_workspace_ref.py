"""Agent workspace references must point at real workspaces.

The agent ``workspace`` field is a free-form string in ``config_json``.
Nothing used to stop an agent from referencing a workspace that does not
exist (e.g. a deleted one) — the list showed a phantom name and, worse,
the run loaded zero MCP tools because the runtime resolves MCPs by that
same name. ``PATCH /api/agents/{id}`` now rejects an unknown named
workspace, and the enriched list flags orphans via ``workspace_exists``.
"""

from __future__ import annotations

import contextlib
import warnings

import agentbox.api.deps as deps
import pytest
from agentbox.api.app import create_app
from agentbox.core.service.agents import AgentService
from fastapi.testclient import TestClient

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")
warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    message=".*PydanticSerializationUnexpectedValue.*",
)


class _ManagedTestClient(TestClient):
    def __del__(self) -> None:
        with contextlib.suppress(Exception):
            self.__exit__(None, None, None)


def _app():
    for fn in (deps.get_settings, deps.get_executor, deps.get_mcp_registry):
        fn.cache_clear()
    client = _ManagedTestClient(create_app())
    client.__enter__()
    return client, AgentService()


def _seed_agent(svc: AgentService) -> None:
    v1 = svc.create_agent(
        agent_id="ws-ref-agent",
        config_json={
            "id": "ws-ref-agent",
            "description": "ws ref test",
            "runner": {"kind": "claude_code", "model": "haiku"},
        },
        author="test",
        changelog="initial",
        prompt_content="You are a test agent.",
        source="ui",
    )
    svc.publish_version("ws-ref-agent", v1["version"], reason="seed")
    svc.activate_version("ws-ref-agent", v1["id"])


def test_patch_rejects_unknown_workspace(isolated_data_dir) -> None:
    client, svc = _app()
    _seed_agent(svc)

    resp = client.patch("/api/agents/ws-ref-agent", json={"workspace": "Stage_actions"})
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["code"] == "unknown_workspace"


def test_patch_accepts_existing_workspace_and_marks_it_present(isolated_data_dir) -> None:
    client, svc = _app()
    _seed_agent(svc)
    svc._db.workspaces.upsert("real_ws")

    resp = client.patch("/api/agents/ws-ref-agent", json={"workspace": "real_ws"})
    assert resp.status_code == 200, resp.text

    row = next(a for a in client.get("/api/agents").json() if a["id"] == "ws-ref-agent")
    assert row["workspace"] == "real_ws"
    assert row["workspace_exists"] is True


def test_null_workspace_allowed(isolated_data_dir) -> None:
    client, svc = _app()
    _seed_agent(svc)
    resp = client.patch("/api/agents/ws-ref-agent", json={"workspace": None})
    assert resp.status_code == 200, resp.text
