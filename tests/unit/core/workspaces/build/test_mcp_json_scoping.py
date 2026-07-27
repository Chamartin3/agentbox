"""Unit tests for _build_mcp_json tool scoping."""
from __future__ import annotations

from agentbox.core.data.workenv import McpRef
from agentbox.core.workspaces.build.engine import _build_mcp_json


def test_disabled_tools_emitted() -> None:
    """Server with disabled_tools produces tools.exclude entry."""
    srv = McpRef(
        name="test-server",
        config={"command": ["python3", "-m", "test"]},
        disabled_tools=["convert_time", "list_resources"],
    )
    result = _build_mcp_json([srv])
    servers = result["mcpServers"]  # type: ignore[index]
    entry = servers["test-server"]  # type: ignore[index]

    assert "tools" in entry
    assert entry["tools"]["exclude"] == ["convert_time", "list_resources"]  # sorted


def test_no_disabled_tools_no_entry() -> None:
    """Server with empty disabled_tools produces no tools key."""
    srv = McpRef(
        name="test-server",
        config={"url": "http://localhost:8080"},
        disabled_tools=[],
    )
    result = _build_mcp_json([srv])
    servers = result["mcpServers"]  # type: ignore[index]
    entry = servers["test-server"]  # type: ignore[index]

    assert "tools" not in entry


def test_url_server_with_disabled_tools() -> None:
    """URL-based server also gets disabled_tools emitted."""
    srv = McpRef(
        name="http-server",
        config={"url": "http://localhost:8080", "transport": "sse"},
        disabled_tools=["dangerous_tool"],
    )
    result = _build_mcp_json([srv])
    servers = result["mcpServers"]  # type: ignore[index]
    entry = servers["http-server"]  # type: ignore[index]

    assert entry["tools"]["exclude"] == ["dangerous_tool"]


def test_multiple_servers() -> None:
    """Multiple servers each get their own disabled_tools."""
    srv_a = McpRef(
        name="server-a",
        config={"command": ["python3", "-m", "a"]},
        disabled_tools=["tool_a1"],
    )
    srv_b = McpRef(
        name="server-b",
        config={"command": ["python3", "-m", "b"]},
        disabled_tools=["tool_b1", "tool_b2"],
    )
    result = _build_mcp_json([srv_a, srv_b])
    servers = result["mcpServers"]  # type: ignore[index]

    assert servers["server-a"]["tools"]["exclude"] == ["tool_a1"]  # type: ignore[index]
    assert servers["server-b"]["tools"]["exclude"] == ["tool_b1", "tool_b2"]  # type: ignore[index]


def test_empty_servers_list() -> None:
    """Empty list produces empty mcpServers dict."""
    result = _build_mcp_json([])
    assert result == {"mcpServers": {}}
