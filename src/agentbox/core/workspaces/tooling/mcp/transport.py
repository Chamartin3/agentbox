"""MCP wire transport — the JSON-RPC HTTP/SSE/stdio client (``McpClient``) and
the one-shot ``discover_tools`` spawn+list helper.

Merges the former client/client.py + client/discovery.py.
"""

from __future__ import annotations

from agentbox.core.data.jsontypes import RawJson

import asyncio
import contextlib
import json
import logging
from collections.abc import Callable
from typing import TypedDict

import httpx
from pydantic import BaseModel, ConfigDict, Field

_log = logging.getLogger(__name__)

MCP_PROTOCOL_VERSION = "2024-11-05"
_CLIENT_INFO = {"name": "agentbox", "version": "0.1.0"}


class McpRawTool(TypedDict, total=False):
    """Raw tool descriptor as returned by an MCP server's ``tools/list``."""

    name: str
    description: str
    inputSchema: RawJson


class McpError(Exception):
    def __init__(self, message: str, code: int = -1) -> None:
        self.code = code
        super().__init__(message)


class _JsonRpcError(BaseModel):
    """JSON-RPC 2.0 error object."""

    code: int = -1
    message: str = "unknown error"


class _JsonRpcResponse(BaseModel):
    """JSON-RPC 2.0 response envelope. ``result`` stays open JSON — its shape is
    method-specific and narrowed by the caller (``initialize`` / ``list_tools``).
    """

    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    result: RawJson = Field(default_factory=dict)
    error: _JsonRpcError | None = None


def _raw_tool(row: RawJson) -> McpRawTool:
    """Narrow one open-JSON tool descriptor into the typed ``McpRawTool``."""
    tool: McpRawTool = {}
    name = row.get("name")
    if isinstance(name, str):
        tool["name"] = name
    description = row.get("description")
    if isinstance(description, str):
        tool["description"] = description
    schema = row.get("inputSchema")
    if isinstance(schema, dict):
        tool["inputSchema"] = schema
    return tool


_STDIO_TIMEOUT = 30.0  # seconds — matches the default httpx timeout on the http path


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
        self._http = http_client or httpx.AsyncClient(
            timeout=30.0, follow_redirects=True
        )
        self._initialized = False
        self._request_id = 0
        # stdio state — set by _ensure_proc(), cleared by close()
        self._proc: asyncio.subprocess.Process | None = None

    async def _ensure_proc(self) -> asyncio.subprocess.Process:
        """Lazily spawn the stdio subprocess; return existing proc if alive."""
        if self._proc is not None and self._proc.returncode is None:
            return self._proc
        if not self._command:
            raise McpError(
                f"stdio transport requires a command for server {self.server_name}"
            )
        self._proc = await asyncio.create_subprocess_exec(
            *self._command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        return self._proc

    async def initialize(self) -> RawJson:
        if self._transport in ("http", "sse") and self._url:
            result = await self._jsonrpc(
                "initialize",
                {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": _CLIENT_INFO,
                },
            )
            self._initialized = True
            return result
        if self._transport == "stdio":
            result = await self._jsonrpc(
                "initialize",
                {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": _CLIENT_INFO,
                },
            )
            self._initialized = True
            return result
        raise McpError(
            f"unsupported transport: {self._transport} for server {self.server_name}"
        )

    async def list_tools(self) -> list[McpRawTool]:
        if not self._initialized:
            await self.initialize()
        result = await self._jsonrpc("tools/list", {})
        raw_tools = result.get("tools")
        if not isinstance(raw_tools, list):
            return []
        return [_raw_tool(row) for row in raw_tools if isinstance(row, dict)]

    async def subscribe_changes(self, callback: Callable[[], None]) -> None:
        if self._transport == "sse" and self._url:
            task = asyncio.create_task(self._sse_listen(callback))
            task.add_done_callback(
                lambda t: t.exception() if not t.cancelled() else None
            )

    # The request body stays a plain ``dict`` (built locally from literals and
    # serialized straight to the wire); the response is validated through the
    # typed ``_JsonRpcResponse`` envelope below.
    async def _jsonrpc(self, method: str, params: dict) -> RawJson:
        self._request_id += 1
        body = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }
        if self._transport in ("http", "sse"):
            assert self._url is not None, "http/sse transport requires a URL"
            return await self._http_request(body)
        if self._transport == "stdio":
            return await self._stdio_request(body)
        raise McpError(f"unsupported transport: {self._transport}")

    async def _http_request(self, body: dict) -> RawJson:
        assert self._url is not None, "http_request requires a URL"
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

        env = _JsonRpcResponse.model_validate(data)
        if env.error is not None:
            raise McpError(env.error.message, env.error.code)
        return env.result

    async def _stdio_request(self, body: dict) -> RawJson:
        """Send one Content-Length-framed JSON-RPC request and read the reply.

        The MCP stdio transport uses the same framing as the Language Server
        Protocol: headers terminated by ``\\r\\n\\r\\n``, then a JSON body of
        exactly ``Content-Length`` bytes.
        """
        proc = await self._ensure_proc()
        assert proc.stdin is not None, "subprocess stdin must be a pipe"
        assert proc.stdout is not None, "subprocess stdout must be a pipe"

        # --- write ---
        payload = json.dumps(body).encode()
        frame = f"Content-Length: {len(payload)}\r\n\r\n".encode() + payload
        try:
            proc.stdin.write(frame)
            await asyncio.wait_for(proc.stdin.drain(), timeout=_STDIO_TIMEOUT)
        except TimeoutError as exc:
            raise McpError(
                f"stdio write timed out for server {self.server_name}"
            ) from exc
        except OSError as exc:
            raise McpError(
                f"stdio write error for server {self.server_name}: {exc}"
            ) from exc

        # --- read headers ---
        try:
            raw_headers = await asyncio.wait_for(
                self._read_stdio_headers(proc.stdout), timeout=_STDIO_TIMEOUT
            )
        except TimeoutError as exc:
            raise McpError(
                f"stdio response timed out for server {self.server_name}"
            ) from exc

        content_length = self._parse_content_length(raw_headers)

        # --- read body ---
        try:
            raw_body = await asyncio.wait_for(
                proc.stdout.readexactly(content_length), timeout=_STDIO_TIMEOUT
            )
        except TimeoutError as exc:
            raise McpError(
                f"stdio body read timed out for server {self.server_name}"
            ) from exc
        except asyncio.IncompleteReadError as exc:
            raise McpError(
                f"stdio connection closed mid-body for server {self.server_name}"
            ) from exc

        # --- parse ---
        try:
            data = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise McpError(f"invalid json from stdio server: {exc}") from exc

        env = _JsonRpcResponse.model_validate(data)
        req_id = body.get("id")
        if env.id != req_id:
            raise McpError(
                f"stdio response id mismatch: expected {req_id}, got {env.id}"
            )
        if env.error is not None:
            raise McpError(env.error.message, env.error.code)
        return env.result

    @staticmethod
    async def _read_stdio_headers(
        reader: asyncio.StreamReader,
    ) -> list[str]:
        """Read lines until the blank line that terminates the header block."""
        headers: list[str] = []
        while True:
            raw = await reader.readline()
            if not raw:
                raise McpError("stdio server closed connection during headers")
            line = raw.decode(errors="replace").rstrip("\r\n")
            if line == "":
                # blank line — end of headers
                break
            headers.append(line)
        return headers

    @staticmethod
    def _parse_content_length(headers: list[str]) -> int:
        """Extract the Content-Length value from a list of header strings."""
        for h in headers:
            if h.lower().startswith("content-length:"):
                value = h.split(":", 1)[1].strip()
                try:
                    length = int(value)
                except ValueError as exc:
                    raise McpError(
                        f"invalid Content-Length value: {value!r}"
                    ) from exc
                if length < 0:
                    raise McpError(f"negative Content-Length: {length}")
                return length
        raise McpError("stdio response missing Content-Length header")

    async def _sse_listen(self, callback: Callable[[], None]) -> None:
        if not self._url:
            return
        event_type = ""
        try:
            async with self._http.stream("GET", self._url) as response:
                async for line in response.aiter_lines():
                    if line.startswith("event: "):
                        event_type = line[7:].strip()
                    elif (
                        line.startswith("data: ")
                        and event_type == "notifications/tools/list_changed"
                    ):
                        callback()
        except Exception:
            pass

    async def close(self) -> None:
        await self._http.aclose()
        if self._proc is not None:
            with contextlib.suppress(Exception):
                self._proc.terminate()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._proc.wait(), timeout=5.0)
            self._proc = None


# ── One-shot discovery (spawn server, list tools) ───────────────────────────

_INITIALIZE = json.dumps(
    {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "agentbox-discovery", "version": "0.1"},
        },
    }
)

_TOOLS_LIST = json.dumps(
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
)


def _extract_tool_names(raw: str) -> list[str]:
    """Parse a JSON-RPC response and return ``result.tools[].name``."""
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return []
    result = obj.get("result")
    if not isinstance(result, dict):
        return []
    tools = result.get("tools") or []
    names: list[str] = []
    for t in tools:
        if isinstance(t, dict) and isinstance(t.get("name"), str):
            names.append(t["name"])
    return names


async def _discover_stdio(
    name: str, command: str, args: list[str], timeout: float
) -> list[str]:
    """Spawn a stdio MCP server and ask for tools/list."""
    cmd = [command, *args]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        payload = (_INITIALIZE + "\n" + _TOOLS_LIST + "\n").encode()
        stdout, _ = await asyncio.wait_for(
            proc.communicate(input=payload), timeout=timeout
        )
    except TimeoutError:
        _log.warning(
            "mcp-discovery: stdio server %r timed out after %ss", name, timeout
        )
        with contextlib.suppress(Exception):
            proc.kill()
        return []
    finally:
        with contextlib.suppress(Exception):
            proc.kill()

    # Parse line by line — the tools/list response is the *second* JSON line
    tools: list[str] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        names = _extract_tool_names(line.decode(errors="replace"))
        if names:
            tools.extend(names)
    return tools


async def _discover_http(name: str, url: str, timeout: float) -> list[str]:
    """POST ``url/tools/list`` and parse the JSON-RPC response."""
    endpoint = url.rstrip("/") + "/tools/list"
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                endpoint,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            return _extract_tool_names(resp.text)
    except Exception as exc:
        _log.warning("mcp-discovery: HTTP server %r failed: %s", name, exc)
        return []


async def _discover_one(server: dict, timeout: float) -> tuple[str, list[str]]:
    name: str = server.get("name", "<unknown>")
    try:
        if "url" in server:
            tools = await _discover_http(name, server["url"], timeout)
        elif "command" in server:
            args: list[str] = server.get("args", [])
            tools = await _discover_stdio(name, server["command"], args, timeout)
        else:
            _log.warning(
                "mcp-discovery: server %r has neither 'url' nor 'command' — skipping",
                name,
            )
            tools = []
    except Exception as exc:
        _log.warning("mcp-discovery: server %r raised unexpected error: %s", name, exc)
        tools = []
    return name, tools


async def discover_tools(
    servers: list[dict], *, timeout: float = 10.0
) -> dict[str, list[str]]:
    """Discover tools from a list of MCP server descriptors.

    Each *server* dict must contain at minimum:
    - ``name`` — a human-readable identifier.
    - Either ``url`` (HTTP/SSE server) **or** ``command`` + optional ``args``
      (stdio server).

    Returns ``{server_name: [tool_name, ...]}``; failures produce an empty
    list for the affected server and are logged at WARNING level.
    """
    if not servers:
        return {}

    tasks = [_discover_one(s, timeout) for s in servers]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    out: dict[str, list[str]] = {}
    for i, result in enumerate(results):
        if isinstance(result, BaseException):
            name = servers[i].get("name", f"server-{i}")
            _log.warning("mcp-discovery: gather error for %r: %s", name, result)
            out[name] = []
        else:
            name, tools = result
            out[name] = tools
    return out
