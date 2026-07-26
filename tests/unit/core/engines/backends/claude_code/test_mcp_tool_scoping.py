"""Tests for per-server MCP tool scoping in the claude_code backend.

Phase A probe findings (Claude Code 2.1.186):
- ``--allowedTools mcp__<server>__<tool>`` is the confirmed, documented
  mechanism for MCP tool scoping (143+ references in the CLI binary).
- A per-server ``tools.exclude`` key in ``.mcp.json`` is not documented;
  ``ClaudeMcpToolsScope`` is modelled in ``schemas.py`` so the emitted
  JSON passes validation if the CLI does honor it silently.

These tests assert the chosen output shape (Option A: emit ``tools.exclude``
into ``.mcp.json`` via ``engine.py``, document via ``schemas.py``) produces
valid config objects that do not raise pydantic ``ValidationError``.
"""

from __future__ import annotations

from agentbox.core.engines.backends.claude_code.schemas import (
    ClaudeMcpConfig,
    ClaudeMcpServerHttp,
    ClaudeMcpServerStdio,
    ClaudeMcpToolsScope,
)
from agentbox.core.workspaces.build.engine import _build_mcp_json
from agentbox.core.data.workenv import McpRef


# ---------------------------------------------------------------------------
# ClaudeMcpToolsScope
# ---------------------------------------------------------------------------


def test_tools_scope_defaults_to_empty_exclude() -> None:
    """ClaudeMcpToolsScope with no args is valid and has empty exclude list."""
    scope = ClaudeMcpToolsScope()
    assert scope.exclude == []


def test_tools_scope_accepts_exclude_list() -> None:
    """ClaudeMcpToolsScope accepts a list of tool names to exclude."""
    scope = ClaudeMcpToolsScope(exclude=["convert_time", "list_resources"])
    assert scope.exclude == ["convert_time", "list_resources"]


# ---------------------------------------------------------------------------
# ClaudeMcpServerHttp with tools field
# ---------------------------------------------------------------------------


def test_http_server_accepts_tools_field() -> None:
    """ClaudeMcpServerHttp with tools.exclude does not raise ValidationError."""
    server = ClaudeMcpServerHttp(
        type="http",
        url="https://example.com/mcp",
        tools=ClaudeMcpToolsScope(exclude=["dangerous_tool"]),
    )
    assert server.tools is not None
    assert server.tools.exclude == ["dangerous_tool"]


def test_http_server_tools_field_optional() -> None:
    """ClaudeMcpServerHttp without tools field is valid (backward compat)."""
    server = ClaudeMcpServerHttp(type="http", url="https://example.com/mcp")
    assert server.tools is None


def test_http_server_model_dump_includes_exclude() -> None:
    """model_dump() on http server with tools produces expected JSON shape."""
    server = ClaudeMcpServerHttp(
        type="sse",
        url="https://example.com/sse",
        tools=ClaudeMcpToolsScope(exclude=["tool_a"]),
    )
    dumped = server.model_dump(exclude_none=True)
    assert dumped["tools"] == {"exclude": ["tool_a"]}


# ---------------------------------------------------------------------------
# ClaudeMcpServerStdio with tools field
# ---------------------------------------------------------------------------


def test_stdio_server_accepts_tools_field() -> None:
    """ClaudeMcpServerStdio with tools.exclude does not raise ValidationError."""
    server = ClaudeMcpServerStdio(
        command="npx",
        args=["-y", "some-mcp-server"],
        tools=ClaudeMcpToolsScope(exclude=["write_file"]),
    )
    assert server.tools is not None
    assert server.tools.exclude == ["write_file"]


def test_stdio_server_tools_field_optional() -> None:
    """ClaudeMcpServerStdio without tools field is valid (backward compat)."""
    server = ClaudeMcpServerStdio(command="npx", args=["-y", "some-mcp-server"])
    assert server.tools is None


def test_stdio_server_model_dump_includes_sorted_exclude() -> None:
    """model_dump() on stdio server with tools produces expected JSON shape."""
    server = ClaudeMcpServerStdio(
        command="uvx",
        args=["mcp-server-time"],
        tools=ClaudeMcpToolsScope(exclude=["convert_time"]),
    )
    dumped = server.model_dump(exclude_none=True)
    assert dumped["tools"] == {"exclude": ["convert_time"]}


# ---------------------------------------------------------------------------
# ClaudeMcpConfig validation with tools.exclude entries
# ---------------------------------------------------------------------------


def test_mcp_config_accepts_servers_with_tools_exclude() -> None:
    """ClaudeMcpConfig validates correctly with mixed server types incl. tools."""
    config = ClaudeMcpConfig(
        mcpServers={
            "time-server": ClaudeMcpServerHttp(
                type="http",
                url="https://time.example.com/mcp",
                tools=ClaudeMcpToolsScope(exclude=["convert_time"]),
            ),
            "fs-server": ClaudeMcpServerStdio(
                command="uvx",
                args=["mcp-server-filesystem"],
            ),
        }
    )
    time_srv = config.mcpServers["time-server"]
    assert isinstance(time_srv, ClaudeMcpServerHttp)
    assert time_srv.tools is not None
    assert "convert_time" in time_srv.tools.exclude


def test_mcp_config_from_dict_with_tools_exclude() -> None:
    """ClaudeMcpConfig.model_validate() accepts the raw dict emitted by engine.py."""
    raw = {
        "mcpServers": {
            "my-server": {
                "command": "uvx",
                "args": ["mcp-server-time"],
                "tools": {"exclude": ["convert_time"]},
            }
        }
    }
    config = ClaudeMcpConfig.model_validate(raw)
    srv = config.mcpServers["my-server"]
    assert isinstance(srv, ClaudeMcpServerStdio)
    assert srv.tools is not None
    assert srv.tools.exclude == ["convert_time"]


# ---------------------------------------------------------------------------
# End-to-end: engine.py emits shape that validates through ClaudeMcpConfig
# ---------------------------------------------------------------------------


def test_build_mcp_json_output_validates_against_schema() -> None:
    """Shape emitted by _build_mcp_json passes ClaudeMcpConfig validation."""
    servers = [
        McpRef(
            name="time-server",
            config={"command": ["uvx", "mcp-server-time"]},
            disabled_tools=["convert_time"],
        ),
        McpRef(
            name="http-server",
            # transport must be explicit to avoid "stdio" default
            config={"url": "https://example.com/mcp", "transport": "http"},
            disabled_tools=[],
        ),
    ]
    raw = _build_mcp_json(servers)

    # Must validate without raising
    config = ClaudeMcpConfig.model_validate(raw)

    time_srv = config.mcpServers["time-server"]
    assert isinstance(time_srv, ClaudeMcpServerStdio)
    assert time_srv.tools is not None
    assert time_srv.tools.exclude == ["convert_time"]

    http_srv = config.mcpServers["http-server"]
    assert isinstance(http_srv, ClaudeMcpServerHttp)
    assert http_srv.tools is None


def test_build_mcp_json_no_disabled_tools_validates_cleanly() -> None:
    """When no tools are disabled, emitted JSON validates without tools key."""
    servers = [
        McpRef(
            name="clean-server",
            # transport must be explicit to avoid "stdio" default for url-based servers
            config={"url": "https://example.com/mcp", "transport": "http"},
            disabled_tools=[],
        ),
    ]
    raw = _build_mcp_json(servers)
    config = ClaudeMcpConfig.model_validate(raw)
    srv = config.mcpServers["clean-server"]
    assert srv.tools is None
