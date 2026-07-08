"""Unit tests for agentbox.core.workspaces.tooling.mcp.transport.discover_tools."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine
from typing import TypeVar
from unittest.mock import patch

import httpx

from agentbox.core.workspaces.tooling.mcp.transport import (
    _extract_tool_names,
    discover_tools,
)

_T = TypeVar("_T")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro: Coroutine[object, object, _T]) -> _T:
    """Run a coroutine in a fresh event loop.

    Use a dedicated loop (created+closed inside this helper) instead of
    ``asyncio.get_event_loop()`` so the loop is guaranteed to be closed
    before the test exits — otherwise pytest's unraisable collection
    surfaces ResourceWarnings from leftover loops in later tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# discover_tools — empty input
# ---------------------------------------------------------------------------


def test_empty_server_list_returns_empty_dict() -> None:
    result = _run(discover_tools([]))
    assert result == {}


# ---------------------------------------------------------------------------
# discover_tools — graceful failure
# ---------------------------------------------------------------------------


def test_stdio_failure_returns_empty_list_for_server() -> None:
    """If the subprocess raises an exception, the server's result is []."""
    server = {"name": "broken-stdio", "command": "nonexistent-bin", "args": []}

    # Patch asyncio.create_subprocess_exec to raise immediately
    with patch(
        "agentbox.core.workspaces.tooling.mcp.transport.asyncio.create_subprocess_exec",
        side_effect=FileNotFoundError("no such file"),
    ):
        result = _run(discover_tools([server], timeout=2.0))

    assert result == {"broken-stdio": []}


def test_http_failure_returns_empty_list_for_server() -> None:
    """If the HTTP request raises, the server's result is []."""
    server = {"name": "broken-http", "url": "http://localhost:19999"}

    with patch(
        "agentbox.core.workspaces.tooling.mcp.transport.httpx.AsyncClient",
        side_effect=httpx.ConnectError("refused"),
    ):
        result = _run(discover_tools([server], timeout=2.0))

    assert result == {"broken-http": []}


def test_mixed_servers_partial_failure() -> None:
    """One failing server must not prevent results for the others."""
    servers = [
        {"name": "bad", "url": "http://localhost:19999"},
        {"name": "also-bad", "command": "nope", "args": []},
    ]

    with (
        patch(
            "agentbox.core.workspaces.tooling.mcp.transport.httpx.AsyncClient",
            side_effect=httpx.ConnectError("refused"),
        ),
        patch(
            "agentbox.core.workspaces.tooling.mcp.transport.asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("no such file"),
        ),
    ):
        result = _run(discover_tools(servers, timeout=2.0))

    assert result == {"bad": [], "also-bad": []}


def test_server_without_url_or_command_returns_empty_list() -> None:
    """A server dict with only a name should return [] gracefully."""
    server = {"name": "mystery"}
    result = _run(discover_tools([server], timeout=2.0))
    assert result == {"mystery": []}


# ---------------------------------------------------------------------------
# _extract_tool_names — helper coverage
# ---------------------------------------------------------------------------


def test_extract_tool_names_valid_response() -> None:
    payload = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {
                "tools": [
                    {"name": "tool_a", "description": "desc a"},
                    {"name": "tool_b", "description": "desc b"},
                ]
            },
        }
    )
    assert _extract_tool_names(payload) == ["tool_a", "tool_b"]


def test_extract_tool_names_empty_tools() -> None:
    payload = json.dumps({"jsonrpc": "2.0", "id": 2, "result": {"tools": []}})
    assert _extract_tool_names(payload) == []


def test_extract_tool_names_invalid_json_returns_empty() -> None:
    assert _extract_tool_names("not json at all") == []


def test_extract_tool_names_no_result_key() -> None:
    payload = json.dumps({"jsonrpc": "2.0", "id": 2, "error": {"code": -1}})
    assert _extract_tool_names(payload) == []
