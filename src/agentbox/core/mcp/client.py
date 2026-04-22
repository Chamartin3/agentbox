from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any, TypedDict

import httpx

MCP_PROTOCOL_VERSION = "2024-11-05"
_CLIENT_INFO = {"name": "agentbox", "version": "0.1.0"}


class McpRawTool(TypedDict, total=False):
    """Raw tool descriptor as returned by an MCP server's ``tools/list``."""

    name: str
    description: str
    inputSchema: dict[str, Any]


class McpError(Exception):
    def __init__(self, message: str, code: int = -1) -> None:
        self.code = code
        super().__init__(message)


class McpClient:
    """Minimal async MCP client over HTTP/SSE/stdio transports.

    Supports ``initialize``, ``list_tools``, and optional
    ``tools/list_changed`` subscription via SSE.
    """

    def __init__(
        self,
        server_name: str,
        *,
        url: str | None = None,
        transport: str = "http",
        command: list[str] | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.server_name = server_name
        self._url = url
        self._transport = transport
        self._command = command
        self._http = http_client or httpx.AsyncClient(timeout=30.0)
        self._initialized = False
        self._request_id = 0

    async def initialize(self) -> dict:
        if self._transport in ("http", "sse") and self._url:
            result = await self._jsonrpc("initialize", {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": _CLIENT_INFO,
            })
            self._initialized = True
            return result
        if self._transport == "stdio":
            raise NotImplementedError("stdio transport not yet implemented")
        raise McpError(f"unsupported transport: {self._transport} for server {self.server_name}")

    async def list_tools(self) -> list[McpRawTool]:
        if not self._initialized:
            await self.initialize()
        result = await self._jsonrpc("tools/list", {})
        return result.get("tools", [])

    async def subscribe_changes(
        self, callback: Callable[[], None]
    ) -> None:
        if self._transport == "sse" and self._url:
            task = asyncio.create_task(self._sse_listen(callback))
            task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)

    async def _jsonrpc(self, method: str, params: dict) -> dict:
        self._request_id += 1
        body = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }
        if self._transport in ("http", "sse") and self._url:
            return await self._http_request(body)
        if self._transport == "stdio":
            return self._stdio_request(body)
        raise McpError(f"unsupported transport: {self._transport}")

    async def _http_request(self, body: dict) -> dict:
        try:
            resp = await self._http.post(
                self._url,
                json=body,
                headers={"Content-Type": "application/json"},
            )
        except httpx.TimeoutException as exc:
            raise McpError(f"request timed out: {exc}") from exc
        except httpx.HTTPError as exc:
            raise McpError(f"http request failed: {exc}") from exc

        if resp.status_code != 200:
            raise McpError(f"http {resp.status_code}: {resp.text}")

        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise McpError(f"invalid json response: {exc}") from exc

        if "error" in data:
            err = data["error"]
            raise McpError(err.get("message", "unknown error"), err.get("code", -1))

        return data.get("result", {})

    def _stdio_request(self, body: dict) -> dict:
        raise NotImplementedError("stdio transport not yet implemented")

    async def _sse_listen(self, callback: Callable[[], None]) -> None:
        if not self._url:
            return
        event_type = ""
        try:
            async with self._http.stream("GET", self._url) as response:
                async for line in response.aiter_lines():
                    if line.startswith("event: "):
                        event_type = line[7:].strip()
                    elif line.startswith("data: ") and event_type == "notifications/tools/list_changed":
                        callback()
        except Exception:
            pass

    async def close(self) -> None:
        await self._http.aclose()
