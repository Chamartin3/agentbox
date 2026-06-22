"""E2E smoke test: agent with a granted tool can invoke it via the MCP server."""

import json
from pathlib import Path

import pytest
from agentbox.core.tools.registry import agent_tool
from agentbox.core.tools.registry import SharedToolRegistry
from pydantic import BaseModel


@pytest.fixture(autouse=True)
def clear_registry():
    SharedToolRegistry.clear()
    yield
    SharedToolRegistry.clear()


class CountIn(BaseModel):
    text: str


class CountOut(BaseModel):
    length: int


def test_agent_tools_mcp_injected_when_grants_exist(tmp_path: Path):
    """Verify that .mcp.json gets the agentbox-agent-tools entry when grants exist."""

    @agent_tool(name="test.count_chars", description="Count characters")
    def count_chars(input: CountIn) -> CountOut:
        return CountOut(length=len(input.text))

    run_dir = tmp_path / "run"
    run_dir.mkdir()

    from agentbox.core.workspaces.generation.inject import (
        inject_agent_tools_mcp,
    )

    inject_agent_tools_mcp(
        run_dir=run_dir,
        grants={"test.count_chars"},
        agent_id="agent-1",
        workdir=tmp_path / "workdir",
        db_path=tmp_path / "store.db",
    )

    config = json.loads((run_dir / ".mcp.json").read_text())
    assert "agentbox-agent-tools" in config["mcpServers"]
    entry = config["mcpServers"]["agentbox-agent-tools"]
    env = entry["env"]
    assert "test.count_chars" in env["AGENTBOX_AGENT_TOOLS_GRANTS_JSON"]
    assert env["AGENTBOX_AGENT_TOOLS_AGENT_ID"] == "agent-1"
    assert entry["args"] == [
        "-m",
        "agentbox.core.workspaces.mcp.servers.agent_tools",
    ]


def test_no_injection_when_no_grants(tmp_path: Path):
    """Verify .mcp.json is NOT written when no grants exist and injection skipped."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    assert not (run_dir / ".mcp.json").exists()
