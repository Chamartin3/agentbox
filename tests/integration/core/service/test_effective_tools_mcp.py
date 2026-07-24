"""Plan 161 — effective_tools returns discovered MCP tools ∩ grants.

Verifies that ``list_effective_tools`` reflects tools from the on-disk MCP
cache without requiring a manual ``POST .../mcp/refresh``.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

from agentbox.core.data import AgentDef
from agentbox.core.data.constants import McpPolicy
from agentbox.core.data.profiles import RunnerProfileCreate
from agentbox.core.db.database import Database
from agentbox.core.service.agents import AgentService
from agentbox.core.service.engines import EngineService
from agentbox.core.service.workspaces import WorkspaceService


def _seed_agent(store: Database, agent_id: str, workspace: str | None = None) -> None:
    """Insert an agent with a claude_code runner profile and activate it."""
    config: dict = {"id": agent_id, "description": "t", "runner": {"kind": "claude_code"}}
    if workspace:
        config["workspace"] = workspace
    agent = AgentDef.model_validate(config)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=UserWarning)
        config_json = agent.model_dump_json()
    row = AgentService().create_version(
        agent_id=agent_id,
        source_path="",
        source_format="db_only",
        content_snapshot=config_json,
        prompt_snapshot="",
        content_hash="x",
        config_json=config_json,
        prompt_content="",
        source="manifest",
    )
    AgentService().activate_version(agent_id, row["id"])


def _write_mcp_cache(cache_dir: Path, server_name: str, tools: list[dict]) -> None:
    """Write a fake MCP discovery cache file for *server_name*."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{server_name}.json").write_text(
        json.dumps({"tools": tools, "cached_at": "2026-07-31T00:00:00Z"}),
        encoding="utf-8",
    )


@pytest.fixture()
def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, str, Path]:
    """Return (agent_id, workspace_name, cache_dir) with DB + env pointing at tmp_path."""
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
    agent_id = "time.agent"
    workspace_name = "time-ws"

    # Create a claude_code runner profile and bind it to the agent.
    profile = EngineService().create_profile(
        RunnerProfileCreate(name="cc", backend="claude_code")
    )
    _seed_agent(Database(tmp_path / "agentbox.sqlite"), agent_id, workspace=workspace_name)
    EngineService().set_agent_runner_profile(agent_id, profile.id)

    # Create the workspace.
    WorkspaceService().create_workspace(workspace_name)

    # Enable the "time-server" MCP server for this workspace.
    WorkspaceService().set_mcp_policy(workspace_name, McpPolicy.ALLOW_ALL_UNLESS_DISABLED)
    WorkspaceService().set_mcp_server_override(
        workspace_name,
        "time-server",
        enabled=True,
        changelog="attach time server",
    )

    cache_dir = tmp_path / "mcp_cache"
    return agent_id, workspace_name, cache_dir


def test_effective_tools_includes_discovered_mcp_tool(
    setup: tuple[str, str, Path],
) -> None:
    """effective_tools returns MCP-sourced tools hydrated from the on-disk cache.

    MCP-01: discovery lists both time tools with schemas off cache — no manual
    /mcp/refresh required.
    """
    agent_id, workspace_name, cache_dir = setup

    # Write a fake MCP cache for the time server with two tools and their schemas.
    _write_mcp_cache(
        cache_dir,
        "time-server",
        [
            {
                "name": "get_current_time",
                "description": "Return the current UTC time.",
                "input_schema": {
                    "type": "object",
                    "properties": {"timezone": {"type": "string"}},
                },
            },
            {
                "name": "convert_time",
                "description": "Convert a time between timezones.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "time": {"type": "string"},
                        "target_tz": {"type": "string"},
                    },
                    "required": ["time", "target_tz"],
                },
            },
        ],
    )

    tools = AgentService().list_effective_tools(agent_id, workspace_name)
    names = {t["name"] for t in tools}

    # Both MCP tools must appear without a manual /mcp/refresh call.
    assert "get_current_time" in names, f"get_current_time missing from {names}"
    assert "convert_time" in names, f"convert_time missing from {names}"


def test_effective_tools_returns_empty_without_cache(
    setup: tuple[str, str, Path],
) -> None:
    """Without a cache file the MCP slice is empty — no fabricated tool list."""
    agent_id, workspace_name, _cache_dir = setup
    # Do NOT write any cache file.
    tools = AgentService().list_effective_tools(agent_id, workspace_name)
    names = {t["name"] for t in tools}
    # MCP tools must not appear when the cache is absent.
    assert "get_current_time" not in names
    assert "convert_time" not in names
