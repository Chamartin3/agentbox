"""Unit tests for McpToolManifest — group expansion, ambiguous refs."""

from __future__ import annotations

import pytest
from agentbox.core.mcp.tool_manifest import McpToolManifest, Tool


def _manifest() -> McpToolManifest:
    m = McpToolManifest()
    m.set_servers({
        "cvman": [
            Tool(name="jobpost_get_all"),
            Tool(name="jobpost_create"),
            Tool(name="cv_upload"),
            Tool(name="cv_get"),
        ],
        "search": [
            Tool(name="search_query"),
            Tool(name="search_index"),
        ],
    })
    return m


def test_servers_property() -> None:
    m = _manifest()
    assert "cvman" in m.servers
    assert "search" in m.servers


def test_server_tools() -> None:
    m = _manifest()
    tools = m.server_tools("cvman")
    assert len(tools) == 4
    assert tools[0].name == "jobpost_get_all"


def test_groups_property() -> None:
    m = _manifest()
    groups = m.groups
    assert "cvman.jobpost.read" in groups
    assert "cvman.jobpost.write" in groups
    assert "cvman.cv.read" in groups
    assert "cvman.cv.write" in groups


def test_resolve_group_explicit_server() -> None:
    m = _manifest()
    tools = m.resolve_group("@cvman:jobpost.read")
    assert len(tools) == 1
    assert tools[0].name == "jobpost_get_all"


def test_resolve_group_implicit() -> None:
    m = _manifest()
    tools = m.resolve_group("@jobpost.read")
    assert len(tools) == 1
    assert tools[0].name == "jobpost_get_all"


def test_resolve_tool_fully_qualified() -> None:
    m = _manifest()
    tool = m.resolve_tool("mcp:cvman/cv_get")
    assert tool is not None
    assert tool.name == "cv_get"


def test_resolve_tool_not_found() -> None:
    m = _manifest()
    assert m.resolve_tool("mcp:cvman/nonexistent") is None


def test_ambiguous_group_raises() -> None:
    m = McpToolManifest()
    m.set_servers({
        "srv1": [Tool(name="data_get")],
        "srv2": [Tool(name="data_get")],
    })
    with pytest.raises(ValueError, match="ambiguous"):
        m.resolve_group("@data.read")


def test_unknown_group_raises() -> None:
    m = _manifest()
    with pytest.raises(ValueError, match="unknown group"):
        m.resolve_group("@nonexistent")


def test_resolve_agent_tools() -> None:
    m = _manifest()
    result = m.resolve_agent_tools(["@jobpost.read"], "cvman")
    assert len(result) == 1
    assert "mcp__cvman__jobpost_get_all" in result


def test_resolve_agent_tools_passthrough() -> None:
    m = _manifest()
    result = m.resolve_agent_tools(["Read", "Write"], "cvman")
    assert result == ["Read", "Write"]


def test_tool_count_all() -> None:
    m = _manifest()
    assert m.tool_count() == 6


def test_tool_count_per_server() -> None:
    m = _manifest()
    assert m.tool_count("cvman") == 4
    assert m.tool_count("search") == 2


def test_group_count() -> None:
    m = _manifest()
    assert m.group_count() > 0


def test_empty_manifest() -> None:
    m = McpToolManifest()
    assert m.tool_count() == 0
    assert m.group_count() == 0
    assert m.servers == {}
    assert m.groups == {}
