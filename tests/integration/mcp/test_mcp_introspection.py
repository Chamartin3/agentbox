"""MCP introspection surface — read system/agent/environment state via MCP.

This is the guardrail behind "don't script the current state, ask the MCP
server". It builds the real introspection server (``agentbox.mcp.server``),
drives it through the in-memory FastMCP client, and asserts the state tools
return coherent data. If a tool drops off the surface or stops reporting
state, this fails instead of some ad-hoc probe script silently rotting.
"""

from __future__ import annotations

import asyncio
from typing import Any

import agentbox.mcp.deps as mcp_deps
import pytest
from agentbox.core.data import AgentDef, RunnerSpec
from agentbox.core.db.database import Database
from agentbox.core.service.agents import AgentService
from agentbox.mcp.server import build_server
from fastmcp import Client, FastMCP

# Tools an operator (or agent) needs to answer "what's the current state?"
# across the three axes the MCP server is meant to cover.
_REQUIRED_TOOLS = {
    # agents
    "list_agents",
    "get_agent",
    "search_agents",
    "list_agent_tags",
    # system activity / runs
    "list_runs",
    "get_run",
    "list_executors",
    # environment
    "render_env_doc",
    "list_host_env_calls",
}


def _call(server: FastMCP, name: str, args: dict[str, Any] | None = None) -> Any:
    async def _run() -> Any:
        async with Client(server) as client:
            result = await client.call_tool(name, args or {})
        return result.data

    return asyncio.run(_run())


def _tool_names(server: FastMCP) -> set[str]:
    async def _run() -> set[str]:
        async with Client(server) as client:
            return {t.name for t in await client.list_tools()}

    return asyncio.run(_run())


@pytest.fixture
def mcp_server(db: Database) -> FastMCP:
    """Introspection server wired to the per-test tmp database.

    ``db`` guarantees a migrated sqlite at ``load_settings().db_path``; the
    services inside ``build_server()`` self-wire to that same path. The
    ``deps`` lru_caches are cleared so a prior test's path can't leak in.
    """
    mcp_deps._get_settings.cache_clear()
    return build_server()


def _seed_agent(agent_id: str = "probe-agent") -> None:
    agent_def = AgentDef(
        id=agent_id,
        description="Introspection probe",
        runner=RunnerSpec(),
    )
    AgentService().create_agent(
        agent_id=agent_id,
        config_json=agent_def.model_dump(mode="python", exclude_none=True, warnings=False),
        prompt_content="# probe\n",
        author="test",
        changelog="seed",
        source="test",
    )


def test_introspection_tools_are_exposed(mcp_server: FastMCP) -> None:
    missing = _REQUIRED_TOOLS - _tool_names(mcp_server)
    assert not missing, f"MCP server is missing state tools: {sorted(missing)}"


def test_list_agents_reports_empty_then_seeded(mcp_server: FastMCP) -> None:
    before = _call(mcp_server, "list_agents")
    assert before["total"] == 0
    assert before["items"] == []

    _seed_agent()

    after = _call(mcp_server, "list_agents")
    assert after["total"] == 1
    assert [a["id"] for a in after["items"]] == ["probe-agent"]


def test_get_agent_roundtrip_and_not_found(mcp_server: FastMCP) -> None:
    _seed_agent()

    found = _call(mcp_server, "get_agent", {"agent_id": "probe-agent"})
    assert found["agent"]["id"] == "probe-agent"

    missing = _call(mcp_server, "get_agent", {"agent_id": "nope"})
    assert missing["error"] == "not_found"


def test_list_executors_is_coherent(mcp_server: FastMCP) -> None:
    result = _call(mcp_server, "list_executors")
    # No runs recorded yet → empty but well-formed; total always matches items.
    assert result["total"] == len(result["items"])
