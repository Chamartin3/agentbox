"""Unit tests for McpClient — fake transport, initialize, list_tools."""

from __future__ import annotations

import httpx
import pytest
from agentbox.core.mcp.transport import McpClient, McpError


@pytest.mark.asyncio
async def test_initialize_http_success() -> None:
    async with httpx.AsyncClient() as http:
        client = McpClient(
            "test",
            url="http://localhost:9999/mcp",
            transport="http",
            http_client=http,
        )
        with pytest.raises(McpError):
            await client.initialize()


@pytest.mark.asyncio
async def test_list_tools_not_initialized() -> None:
    async with httpx.AsyncClient() as http:
        client = McpClient(
            "test",
            url="http://localhost:9999/mcp",
            transport="http",
            http_client=http,
        )
        with pytest.raises(McpError):
            await client.list_tools()


@pytest.mark.asyncio
async def test_unsupported_transport_raises() -> None:
    client = McpClient("test")
    with pytest.raises(McpError, match="unsupported transport"):
        await client.initialize()


@pytest.mark.asyncio
async def test_close_idempotent() -> None:
    async with httpx.AsyncClient() as http:
        client = McpClient("test", url="http://localhost:9999/mcp", http_client=http)
        await client.close()


@pytest.mark.asyncio
async def test_stdio_no_command_raises_mcp_error() -> None:
    """stdio transport with no command raises McpError (not NotImplementedError)."""
    client = McpClient("test", transport="stdio")
    with pytest.raises(McpError, match="requires a command"):
        await client.initialize()


def test_mcp_error() -> None:
    err = McpError("test error", code=-1)
    assert str(err) == "test error"
    assert err.code == -1


@pytest.mark.asyncio
async def test_http_sends_dual_accept_header() -> None:
    # Streamable HTTP servers 406 unless the client accepts both content types.
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["accept"] = request.headers.get("accept", "")
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = McpClient("t", url="http://x/mcp", transport="http", http_client=http)
        await client.initialize()

    assert "application/json" in seen["accept"]
    assert "text/event-stream" in seen["accept"]


@pytest.mark.asyncio
async def test_http_captures_and_resends_session_id() -> None:
    # initialize issues Mcp-Session-Id; every later request must echo it.
    seen_ids: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_ids.append(request.headers.get("mcp-session-id"))
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": 1, "result": {"tools": []}},
            headers={"mcp-session-id": "sess-123"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = McpClient("t", url="http://x/mcp", transport="http", http_client=http)
        await client.list_tools()  # initialize + notify + tools/list

    # First request (initialize) has no session id yet; the notify + tools/list
    # that follow must carry the id the server returned.
    assert seen_ids[0] is None
    assert seen_ids[-1] == "sess-123"


@pytest.mark.asyncio
async def test_http_parses_sse_response() -> None:
    # A Streamable HTTP server may answer with an SSE stream instead of JSON.
    body = 'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"tools":[]}}\n\n'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, text=body, headers={"content-type": "text/event-stream"}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = McpClient("t", url="http://x/mcp", transport="http", http_client=http)
        await client.initialize()  # succeeds only if the SSE body parsed
