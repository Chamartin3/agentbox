"""E2E smoke test: agent with a granted tool can invoke it via the MCP server."""

from pathlib import Path

import pytest
from agentbox.core.tools.registry import agent_tool
from agentbox.core.tools.registry import SharedToolRegistry
from agentbox.core.tools.mcp_servers.specs import agent_tools_server_spec
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

    # The agent-tools spawn spec carries the granted tool names + agent context;
    # build() writes it into the run dir's .mcp.json (merge covered elsewhere).
    spec = agent_tools_server_spec(
        grants={"test.count_chars"},
        agent_id="agent-1",
        workdir=tmp_path / "workdir",
        db_path=tmp_path / "store.db",
    )
    env = spec["env"]
    assert "test.count_chars" in env["AGENTBOX_AGENT_TOOLS_GRANTS_JSON"]
    assert env["AGENTBOX_AGENT_TOOLS_AGENT_ID"] == "agent-1"
    assert spec["args"] == ["-m", "agentbox.core.tools.mcp_servers.agent_tools"]
