"""Unit tests for McpClient stdio transport.

Uses a fake in-process stdio server (asyncio pipes) to verify
newline-delimited JSON-RPC framing, request/response, and close() cleanup
without spawning real subprocesses.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentbox.core.workspaces.tooling.mcp.transport import McpClient, McpError


# ---------------------------------------------------------------------------
# Helpers — build a fake subprocess process mock backed by asyncio streams
# ---------------------------------------------------------------------------


def _frame(payload: bytes) -> bytes:
    """Frame *payload* as one newline-delimited JSON-RPC message."""
    return payload + b"\n"


def _jsonrpc_response(req_id: int, result: dict) -> bytes:
    body = json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result}).encode()
    return _frame(body)


def _jsonrpc_error_response(req_id: int, code: int, message: str) -> bytes:
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": code, "message": message},
        }
    ).encode()
    return _frame(body)


async def _make_fake_proc(
    *response_payloads: bytes,
) -> tuple[MagicMock, asyncio.StreamReader, asyncio.StreamWriter]:
    """Build a fake asyncio.subprocess.Process with pre-canned stdout bytes.

    Returns (mock_proc, reader, writer).  The writer is discarded after
    construction; the reader is loaded with *response_payloads* concatenated.
    """
    # Build a real StreamReader loaded with the canned response bytes
    reader = asyncio.StreamReader()
    for payload in response_payloads:
        reader.feed_data(payload)
    reader.feed_eof()

    # A StreamWriter whose .write() / .drain() we swallow
    transport = MagicMock()
    protocol = asyncio.StreamReaderProtocol(reader)
    loop = asyncio.get_running_loop()
    writer = asyncio.StreamWriter(transport, protocol, reader, loop)

    mock_proc = MagicMock()
    mock_proc.returncode = None
    mock_proc.stdin = writer
    mock_proc.stdout = reader
    mock_proc.terminate = MagicMock()
    mock_proc.wait = AsyncMock(return_value=0)
    return mock_proc, reader, writer


# ---------------------------------------------------------------------------
# framing — the response reader must skip notifications and log noise
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stdio_skips_notifications_and_noise() -> None:
    """The reader ignores non-JSON lines and id-less notifications, returning
    the response whose id matches the request."""
    noise = b"Starting server...\n"
    notification = json.dumps({"jsonrpc": "2.0", "method": "log", "params": {}}).encode() + b"\n"
    init_response = _jsonrpc_response(1, {"protocolVersion": "2024-11-05"})
    mock_proc, reader, writer = await _make_fake_proc(noise, notification, init_response)

    client = McpClient("test-server", transport="stdio", command=["fake-mcp"])
    with patch.object(client, "_ensure_proc", AsyncMock(return_value=mock_proc)):
        result = await client.initialize()

    assert result == {"protocolVersion": "2024-11-05"}


# ---------------------------------------------------------------------------
# initialize() — stdio path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stdio_initialize_success() -> None:
    """initialize() over stdio returns the server's result dict."""
    init_response = _jsonrpc_response(1, {"protocolVersion": "2024-11-05"})
    mock_proc, reader, writer = await _make_fake_proc(init_response)

    client = McpClient("test-server", transport="stdio", command=["fake-mcp"])
    with patch.object(client, "_ensure_proc", AsyncMock(return_value=mock_proc)):
        result = await client.initialize()

    assert result == {"protocolVersion": "2024-11-05"}
    assert client._initialized is True


@pytest.mark.asyncio
async def test_stdio_no_command_raises() -> None:
    """stdio without command raises McpError before spawning."""
    client = McpClient("test-server", transport="stdio")
    with pytest.raises(McpError, match="requires a command"):
        await client.initialize()


# ---------------------------------------------------------------------------
# list_tools() — stdio path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stdio_list_tools_returns_tools() -> None:
    """list_tools() calls initialize then tools/list and returns tool dicts."""
    tools_payload = [
        {"name": "read_file", "description": "Read a file", "inputSchema": {}},
        {"name": "write_file", "description": "Write a file", "inputSchema": {}},
    ]
    init_response = _jsonrpc_response(1, {"protocolVersion": "2024-11-05"})
    list_response = _jsonrpc_response(2, {"tools": tools_payload})

    mock_proc, reader, writer = await _make_fake_proc(init_response, list_response)

    client = McpClient("test-server", transport="stdio", command=["fake-mcp"])
    with patch.object(client, "_ensure_proc", AsyncMock(return_value=mock_proc)):
        tools = await client.list_tools()

    assert len(tools) == 2
    assert tools[0]["name"] == "read_file"
    assert tools[1]["name"] == "write_file"


@pytest.mark.asyncio
async def test_stdio_list_tools_empty() -> None:
    """list_tools() with empty tools list returns []."""
    init_response = _jsonrpc_response(1, {"protocolVersion": "2024-11-05"})
    list_response = _jsonrpc_response(2, {"tools": []})

    mock_proc, reader, writer = await _make_fake_proc(init_response, list_response)

    client = McpClient("test-server", transport="stdio", command=["fake-mcp"])
    with patch.object(client, "_ensure_proc", AsyncMock(return_value=mock_proc)):
        tools = await client.list_tools()

    assert tools == []


# ---------------------------------------------------------------------------
# list_resources() — stdio path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stdio_list_resources_returns_resources() -> None:
    """list_resources() calls initialize then resources/list and narrows rows."""
    resources_payload = [
        {"uri": "file:///a.txt", "name": "a", "description": "first", "mimeType": "text/plain"},
        {"uri": "file:///b.txt", "name": "b"},
    ]
    init_response = _jsonrpc_response(1, {"protocolVersion": "2024-11-05"})
    list_response = _jsonrpc_response(2, {"resources": resources_payload})

    mock_proc, reader, writer = await _make_fake_proc(init_response, list_response)

    client = McpClient("test-server", transport="stdio", command=["fake-mcp"])
    with patch.object(client, "_ensure_proc", AsyncMock(return_value=mock_proc)):
        resources = await client.list_resources()

    assert [r["uri"] for r in resources] == ["file:///a.txt", "file:///b.txt"]
    assert resources[0]["description"] == "first"
    assert "description" not in resources[1]  # absent fields are dropped, not None


@pytest.mark.asyncio
async def test_stdio_list_resources_unsupported_returns_empty() -> None:
    """A server without resources replies method-not-found → returns []."""
    init_response = _jsonrpc_response(1, {"protocolVersion": "2024-11-05"})
    err_response = _jsonrpc_error_response(2, -32601, "Method not found")

    mock_proc, reader, writer = await _make_fake_proc(init_response, err_response)

    client = McpClient("test-server", transport="stdio", command=["fake-mcp"])
    with patch.object(client, "_ensure_proc", AsyncMock(return_value=mock_proc)):
        resources = await client.list_resources()

    assert resources == []


# ---------------------------------------------------------------------------
# JSON-RPC error in response body
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stdio_jsonrpc_error_raises_mcp_error() -> None:
    """A JSON-RPC error in the response body surfaces as McpError."""
    error_response = _jsonrpc_error_response(1, -32601, "Method not found")
    mock_proc, reader, writer = await _make_fake_proc(error_response)

    client = McpClient("test-server", transport="stdio", command=["fake-mcp"])
    with patch.object(client, "_ensure_proc", AsyncMock(return_value=mock_proc)):
        with pytest.raises(McpError, match="Method not found"):
            await client.initialize()


# ---------------------------------------------------------------------------
# close() — subprocess termination
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_terminates_proc() -> None:
    """close() terminates the subprocess and clears _proc."""
    mock_proc = MagicMock()
    mock_proc.returncode = None
    mock_proc.terminate = MagicMock()
    mock_proc.wait = AsyncMock(return_value=0)

    client = McpClient("test-server", transport="stdio", command=["fake-mcp"])
    client._proc = mock_proc

    with patch.object(client._http, "aclose", AsyncMock()):
        await client.close()

    mock_proc.terminate.assert_called_once()
    assert client._proc is None


@pytest.mark.asyncio
async def test_close_no_proc_is_safe() -> None:
    """close() with no spawned proc completes without error."""
    client = McpClient("test-server", transport="stdio", command=["fake-mcp"])
    assert client._proc is None
    with patch.object(client._http, "aclose", AsyncMock()):
        await client.close()  # must not raise


@pytest.mark.asyncio
async def test_close_already_terminated_proc_is_safe() -> None:
    """close() when proc has already exited does not raise."""
    mock_proc = MagicMock()
    mock_proc.returncode = 0  # already done
    mock_proc.terminate = MagicMock()
    mock_proc.wait = AsyncMock(return_value=0)

    client = McpClient("test-server", transport="stdio", command=["fake-mcp"])
    client._proc = mock_proc

    with patch.object(client._http, "aclose", AsyncMock()):
        await client.close()

    assert client._proc is None
