"""http.fetch capability tool."""

from __future__ import annotations

import urllib.error
import urllib.request
from collections.abc import Callable

from agentbox.core.workspaces.mcp.servers.host_env.context import HostEnvContext
from agentbox.core.workspaces.permissions import GrantViolation, check_capability
from fastmcp import FastMCP


def register(mcp: FastMCP, ctx_factory: Callable[[], HostEnvContext]) -> None:
    @mcp.tool(
        name="http.fetch",
        description="HTTP request to an allowlisted host. Requires http.fetch grant.",
    )
    def http_fetch(
        url: str,
        method: str = "GET",
        body: str | None = None,
        headers: dict | None = None,
    ) -> dict:
        ctx = ctx_factory()
        try:
            check_capability(ctx.grants, "http.fetch", {"url": url, "method": method})
        except GrantViolation as exc:
            ctx.audit(
                "http.fetch",
                {"url": url, "method": method},
                outcome="denied",
                error=str(exc),
            )
            raise
        req = urllib.request.Request(url, method=method.upper())
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        if body:
            req.data = body.encode()
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                status = resp.status
                text = resp.read().decode(errors="replace")
        except urllib.error.HTTPError as exc:
            ctx.audit("http.fetch", {"url": url}, outcome="http_error", error=str(exc))
            return {"status": exc.code, "body": exc.read().decode(errors="replace")}
        except Exception as exc:
            ctx.audit("http.fetch", {"url": url}, outcome="error", error=str(exc))
            raise
        ctx.audit("http.fetch", {"url": url, "status": status}, outcome="ok")
        return {"status": status, "body": text}
