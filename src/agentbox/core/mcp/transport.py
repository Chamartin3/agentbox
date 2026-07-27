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


class McpRawResource(TypedDict, total=False):
    """Raw resource descriptor as returned by an MCP server's ``resources/list``."""

    uri: str
    name: str
    description: str
    mimeType: str


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


def _raw_resource(row: RawJson) -> McpRawResource:
    """Narrow one open-JSON resource descriptor into ``McpRawResource``."""
    res: McpRawResource = {}
    for key in ("uri", "name", "description", "mimeType"):
        val = row.get(key)
        if isinstance(val, str):
            res[key] = val  # type: ignore[literal-required]
    return res


_STDIO_TIMEOUT = 30.0  # seconds — matches the default httpx timeout on the http path


def _parse_sse_json(text: str) -> RawJson:
    """Extract the JSON-RPC payload from an SSE response (first `data:` line)."""
    for line in text.splitlines():
        if line.startswith("data:"):
            try:
                return json.loads(line[len("data:") :].strip())
            except json.JSONDecodeError as exc:
                raise McpError(f"invalid sse json response: {exc}") from exc
    raise McpError("sse response contained no data line")


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
        # Streamable HTTP is stateful: initialize returns an Mcp-Session-Id that
        # must be echoed on every later request, or the server 400s.
        self._session_id: str | None = None
        # stdio state — set by _ensure_proc(), cleared by close()
        self._proc: asyncio.subprocess.Process | None = None
        # Background task draining the child's stderr. Without it a child that
        # logs to stderr fills the 64K pipe buffer and blocks, while we block
        # reading stdout → deadlock (a hung introspection with no response).
        self._stderr_drain: asyncio.Task[None] | None = None

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
        # Continuously drain stderr so a chatty child can't deadlock on a full
        # pipe while we read stdout. Runs until the proc exits or close() cancels.
        if self._proc.stderr is not None:
            self._stderr_drain = asyncio.create_task(
                self._drain_stderr(self._proc.stderr)
            )
        return self._proc

    async def _drain_stderr(self, stderr: asyncio.StreamReader) -> None:
        """Silently consume the child's stderr to prevent a pipe-buffer deadlock."""
        with contextlib.suppress(Exception):
            while True:
                if not await stderr.readline():
                    break

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
            # Same handshake contract as stdio: acknowledge initialize before
            # the server will serve tools/list. Carries the captured session id.
            await self._http_notify("notifications/initialized", {})
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
            # MCP requires the client to acknowledge initialize before the
            # server will serve requests. Notifications carry no id / reply.
            await self._stdio_notify("notifications/initialized", {})
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

    async def list_resources(self) -> list[McpRawResource]:
        """List the server's resources. Returns ``[]`` when the server does not
        implement ``resources/list`` (it replies with a method-not-found error)."""
        if not self._initialized:
            await self.initialize()
        try:
            result = await self._jsonrpc("resources/list", {})
        except McpError:
            return []
        raw = result.get("resources")
        if not isinstance(raw, list):
            return []
        return [_raw_resource(row) for row in raw if isinstance(row, dict)]

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

    def _http_headers(self) -> dict[str, str]:
        # MCP Streamable HTTP: server may answer with JSON or an SSE stream, so
        # the client must accept both or it 406s. The session id (once issued by
        # initialize) must ride along on every later request or the server 400s.
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id is not None:
            headers["Mcp-Session-Id"] = self._session_id
        return headers

    async def _http_request(self, body: dict) -> RawJson:
        assert self._url is not None, "http_request requires a URL"
        try:
            resp = await self._http.post(
                self._url, json=body, headers=self._http_headers()
            )
        except httpx.TimeoutException as exc:
            raise McpError(f"request timed out: {exc}") from exc
        except httpx.HTTPError as exc:
            raise McpError(f"http request failed: {exc}") from exc

        # Capture the session id the server hands back on initialize.
        session = resp.headers.get("mcp-session-id")
        if session:
            self._session_id = session

        if resp.status_code != 200:
            raise McpError(f"http {resp.status_code}: {resp.text}")

        # Streamable HTTP servers reply with either application/json or an SSE
        # stream; for a single request the SSE body is one `data:` JSON line.
        if "text/event-stream" in resp.headers.get("content-type", ""):
            data = _parse_sse_json(resp.text)
        else:
            try:
                data = resp.json()
            except json.JSONDecodeError as exc:
                raise McpError(f"invalid json response: {exc}") from exc

        env = _JsonRpcResponse.model_validate(data)
        if env.error is not None:
            raise McpError(env.error.message, env.error.code)
        return env.result

    async def _stdio_write(self, message: dict) -> None:
        """Write one newline-delimited JSON-RPC message to the subprocess."""
        proc = await self._ensure_proc()
        assert proc.stdin is not None, "subprocess stdin must be a pipe"
        payload = (json.dumps(message) + "\n").encode()
        try:
            proc.stdin.write(payload)
            await asyncio.wait_for(proc.stdin.drain(), timeout=_STDIO_TIMEOUT)
        except (TimeoutError, OSError) as exc:
            raise McpError(
                f"stdio write error for server {self.server_name}: {exc}"
            ) from exc

    async def _stdio_notify(self, method: str, params: dict) -> None:
        """Fire-and-forget a JSON-RPC notification (no id, no reply)."""
        await self._stdio_write({"jsonrpc": "2.0", "method": method, "params": params})

    async def _http_notify(self, method: str, params: dict) -> None:
        """POST a JSON-RPC notification. The server replies 202 with no body —
        it is not a request, so we don't parse a result, only surface transport
        errors."""
        assert self._url is not None, "http_notify requires a URL"
        body = {"jsonrpc": "2.0", "method": method, "params": params}
        try:
            resp = await self._http.post(
                self._url, json=body, headers=self._http_headers()
            )
        except httpx.HTTPError as exc:
            raise McpError(f"http notify failed: {exc}") from exc
        if resp.status_code >= 400:
            raise McpError(f"http {resp.status_code}: {resp.text}")

    async def _stdio_request(self, body: dict) -> RawJson:
        """Send one newline-delimited JSON-RPC request and read the reply.

        The MCP stdio transport frames each message as a single line of JSON
        (messages MUST NOT contain embedded newlines) — NOT the LSP-style
        ``Content-Length`` header framing. Servers interleave notifications
        and log noise, so read lines until the response whose ``id`` matches
        the request; skip everything else.
        """
        proc = await self._ensure_proc()
        assert proc.stdout is not None, "subprocess stdout must be a pipe"
        await self._stdio_write(body)

        req_id = body.get("id")
        while True:
            try:
                raw = await asyncio.wait_for(
                    proc.stdout.readline(), timeout=_STDIO_TIMEOUT
                )
            except TimeoutError as exc:
                raise McpError(
                    f"stdio response timed out for server {self.server_name}"
                ) from exc
            if not raw:
                raise McpError(
                    f"stdio server {self.server_name} closed connection"
                )
            line = raw.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue  # non-JSON log line on stdout — skip
            if not isinstance(data, dict) or "id" not in data:
                continue  # a notification or unrelated message
            env = _JsonRpcResponse.model_validate(data)
            if env.id != req_id:
                continue  # reply to a different in-flight request
            if env.error is not None:
                raise McpError(env.error.message, env.error.code)
            return env.result

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
        if self._stderr_drain is not None:
            self._stderr_drain.cancel()
            # Awaiting a cancelled task re-raises CancelledError, which is a
            # BaseException (not Exception) — suppress BaseException so cleanup
            # never surfaces as a 500.
            with contextlib.suppress(BaseException):
                await self._stderr_drain
            self._stderr_drain = None
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
