"""E2E smoke test: agent with a granted tool can invoke it via the MCP server."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from agentbox.agent_tools.decorator import agent_tool
from agentbox.agent_tools.registry import SharedToolRegistry
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
    """Verify that claude_mcp.json gets the agentbox-agent-tools entry when grants exist."""

    @agent_tool(name="test.count_chars", description="Count characters")
    def count_chars(input: CountIn) -> CountOut:
        return CountOut(length=len(input.text))

    run_dir = tmp_path / "run"
    run_dir.mkdir()

    from agentbox.core.run.executor import RunExecutor

    executor = MagicMock(spec=RunExecutor)
    executor.settings = MagicMock()
    executor.settings.db_path = tmp_path / "store.db"

    RunExecutor._inject_agent_tools_mcp(
        executor,
        run_dir=run_dir,
        grants={"test.count_chars"},
        agent_id="agent-1",
        workdir=tmp_path / "workdir",
    )

    config = json.loads((run_dir / "claude_mcp.json").read_text())
    assert "agentbox-agent-tools" in config["mcpServers"]
    entry = config["mcpServers"]["agentbox-agent-tools"]
    env = entry["env"]
    assert "test.count_chars" in env["AGENTBOX_AGENT_TOOLS_GRANTS_JSON"]
    assert env["AGENTBOX_AGENT_TOOLS_AGENT_ID"] == "agent-1"
    assert entry["args"] == [
        "-m",
        "agentbox.core.workspace.mcp.servers.agent_tools",
    ]


def test_no_injection_when_no_grants(tmp_path: Path):
    """Verify claude_mcp.json is NOT written when no grants exist and injection skipped."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    assert not (run_dir / "claude_mcp.json").exists()
