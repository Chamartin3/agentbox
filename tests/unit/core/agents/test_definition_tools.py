"""Agent-facing tool authorization (plan 122): available_tools / effective_tools."""

from __future__ import annotations

from agentbox.core.agents.definition.tools import available_tools, effective_tools
from agentbox.core.data import AgentDef, RunnerSpec
from agentbox.core.data.payload_types import ToolInfo
from agentbox.core.data import CanonicalTool


def _agent(*, allowed: list[str] | None = None, forbidden: list[str] | None = None) -> AgentDef:
    agent = AgentDef(id="test.tools", description="t", runner=RunnerSpec())
    runtime: dict[str, list[str]] = {}
    if allowed is not None:
        runtime["allowed_tools"] = allowed
    if forbidden is not None:
        runtime["forbidden_tools"] = forbidden
    agent.__dict__["_config_json"] = {"runtime": runtime}
    return agent


def _mcp(name: str) -> ToolInfo:
    return ToolInfo(name=name, source="mcp", native=None)


def test_available_tools_unions_native_and_catalog() -> None:
    got = available_tools(
        native=[CanonicalTool.FS_READ, CanonicalTool.SHELL_EXEC],
        workspace_catalog=[_mcp("mcp.search")],
    )
    names = [t["name"] for t in got]
    assert names == sorted(names)  # stable, sorted
    assert set(names) == {"fs.read", "shell.exec", "mcp.search"}
    assert next(t for t in got if t["name"] == "fs.read")["source"] == "builtin"


def test_available_tools_catalog_wins_on_collision() -> None:
    # A workspace entry with the same name as a built-in keeps its richer source.
    got = available_tools(
        native=[CanonicalTool.FS_READ],
        workspace_catalog=[ToolInfo(name="fs.read", source="mcp", native="Read")],
    )
    assert len(got) == 1
    assert got[0]["source"] == "mcp"


def test_effective_no_lists_returns_all() -> None:
    available = available_tools(native=[CanonicalTool.FS_READ, CanonicalTool.SHELL_EXEC])
    got = effective_tools(_agent(), available)
    assert {t["name"] for t in got} == {"fs.read", "shell.exec"}


def test_effective_allow_only_unchanged_behavior() -> None:
    available = available_tools(native=[CanonicalTool.FS_READ, CanonicalTool.SHELL_EXEC])
    got = effective_tools(_agent(allowed=["fs.read"]), available)
    assert {t["name"] for t in got} == {"fs.read"}


def test_effective_forbidden_only() -> None:
    available = available_tools(native=[CanonicalTool.FS_READ, CanonicalTool.SHELL_EXEC])
    got = effective_tools(_agent(forbidden=["shell.exec"]), available)
    assert {t["name"] for t in got} == {"fs.read"}


def test_effective_allow_and_forbidden() -> None:
    available = available_tools(
        native=[CanonicalTool.FS_READ, CanonicalTool.FS_WRITE, CanonicalTool.SHELL_EXEC]
    )
    got = effective_tools(
        _agent(allowed=["fs.read", "fs.write", "shell.exec"], forbidden=["shell.exec"]),
        available,
    )
    assert {t["name"] for t in got} == {"fs.read", "fs.write"}


def test_effective_forbidden_not_available_is_noop() -> None:
    available = available_tools(native=[CanonicalTool.FS_READ])
    got = effective_tools(_agent(forbidden=["shell.exec"]), available)
    assert {t["name"] for t in got} == {"fs.read"}
