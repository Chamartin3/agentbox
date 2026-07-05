"""Unit tests for McpClient — fake transport, initialize, list_tools."""

from __future__ import annotations

import httpx
import pytest
from agentbox.core.mcp.client.client import McpClient, McpError


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
async def test_stdio_not_implemented() -> None:
    client = McpClient("test", command=["echo"], transport="stdio")
    with pytest.raises(NotImplementedError):
        await client.initialize()


def test_mcp_error() -> None:
    err = McpError("test error", code=-1)
    assert str(err) == "test error"
    assert err.code == -1
