"""shell.exec capability tool."""

from __future__ import annotations

import subprocess
from collections.abc import Callable

from agentbox.core.tools.canonical import CanonicalTool
from agentbox.core.mcp.servers.host_env.context import HostEnvContext
from agentbox.core.tools.grants import GrantViolation, check_capability
from fastmcp import FastMCP


def register(mcp: FastMCP, ctx_factory: Callable[[], HostEnvContext]) -> None:
    @mcp.tool(
        name=CanonicalTool.SHELL_EXEC.value,
        description="Run an allowlisted shell command. Requires shell.exec grant.",
    )
    def shell_exec(cmd: str, cwd: str | None = None, timeout: int = 30) -> dict:
        ctx = ctx_factory()
        try:
            check_capability(ctx.grants, CanonicalTool.SHELL_EXEC, {"cmd": cmd})
        except GrantViolation as exc:
            ctx.audit(CanonicalTool.SHELL_EXEC, {"cmd": cmd}, outcome="denied", error=str(exc))
            raise
        grant = ctx.grants.get(CanonicalTool.SHELL_EXEC) or {}
        effective_timeout = int(grant.get("timeout_seconds", timeout))
        effective_cwd = cwd or grant.get("cwd") or None
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                cwd=effective_cwd,
            )
            outcome = "ok"
            error = None
        except subprocess.TimeoutExpired:
            ctx.audit(CanonicalTool.SHELL_EXEC, {"cmd": cmd}, outcome="timeout", error="timed out")
            raise
        ctx.audit(CanonicalTool.SHELL_EXEC, {"cmd": cmd}, outcome=outcome, error=error)
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
