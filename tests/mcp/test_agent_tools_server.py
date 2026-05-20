import asyncio

import pytest
from agentbox.agent_tools.decorator import agent_tool
from agentbox.agent_tools.registry import SharedToolRegistry
from agentbox.core.workspace.mcp.servers.agent_tools.context import AgentToolsContext
from agentbox.core.workspace.mcp.servers.agent_tools.server import build_server
from pydantic import BaseModel


@pytest.fixture(autouse=True)
def clear_registry():
    SharedToolRegistry.clear()
    yield
    SharedToolRegistry.clear()


class EchoIn(BaseModel):
    text: str


class EchoOut(BaseModel):
    echoed: str


@pytest.fixture
def echo_tool():
    @agent_tool(name="test.echo", description="Echo input")
    def echo(input: EchoIn) -> EchoOut:
        return EchoOut(echoed=input.text)

    return echo


@pytest.fixture
def ctx_granted(tmp_path):
    return AgentToolsContext(
        grants=frozenset(["test.echo"]),
        agent_id="agent-1",
        run_id="run-1",
        workdir=tmp_path,
        db_path=tmp_path / "test.db",
    )


@pytest.fixture
def ctx_no_grants(tmp_path):
    return AgentToolsContext(
        grants=frozenset(),
        agent_id="agent-1",
        run_id="run-1",
        workdir=tmp_path,
        db_path=tmp_path / "test.db",
    )


def test_granted_tool_is_registered(echo_tool, ctx_granted):
    server = build_server(ctx=ctx_granted)

    async def _list():
        return await server.list_tools()

    tools = asyncio.run(_list())
    tool_names = [t.name for t in tools]
    assert "test.echo" in tool_names


def test_ungranted_tool_is_registered(echo_tool, ctx_no_grants):
    server = build_server(ctx=ctx_no_grants)

    async def _list():
        return await server.list_tools()

    tools = asyncio.run(_list())
    tool_names = [t.name for t in tools]
    assert "test.echo" in tool_names


def test_context_from_env(monkeypatch, tmp_path):
    import json

    monkeypatch.setenv("AGENTBOX_AGENT_TOOLS_GRANTS_JSON", json.dumps(["cv.score"]))
    monkeypatch.setenv("AGENTBOX_AGENT_TOOLS_AGENT_ID", "agent-abc")
    monkeypatch.setenv("AGENTBOX_AGENT_TOOLS_RUN_ID", "run-xyz")
    monkeypatch.setenv("AGENTBOX_AGENT_TOOLS_WORKDIR", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_DB_PATH", str(tmp_path / "db.sqlite"))
    ctx = AgentToolsContext.from_env()
    assert ctx.grants == frozenset(["cv.score"])
    assert ctx.agent_id == "agent-abc"
    assert ctx.is_granted("cv.score")
    assert not ctx.is_granted("other.tool")


def test_tool_raises_on_failure(echo_tool, ctx_granted):
    @agent_tool(name="test.fail", description="Always fails")
    def fail(input: EchoIn) -> EchoOut:
        raise RuntimeError("simulated failure")

    with pytest.raises(RuntimeError, match="simulated failure"):
        fail(EchoIn(text="hello"))


def test_build_server_resolves_context_from_env(echo_tool, monkeypatch, tmp_path):

    monkeypatch.setenv("AGENTBOX_AGENT_TOOLS_GRANTS_JSON", "[]")
    monkeypatch.setenv("AGENTBOX_AGENT_TOOLS_AGENT_ID", "agent-1")
    monkeypatch.setenv("AGENTBOX_AGENT_TOOLS_RUN_ID", "run-1")
    monkeypatch.setenv("AGENTBOX_AGENT_TOOLS_WORKDIR", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_DB_PATH", str(tmp_path / "db.sqlite"))

    server = build_server()

    async def _list():
        return await server.list_tools()

    tools = asyncio.run(_list())
    tool_names = [t.name for t in tools]
    assert "test.echo" in tool_names
