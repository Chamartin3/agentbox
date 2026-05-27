"""shell.exec capability tool."""

from __future__ import annotations

import subprocess

from agentbox.core.workspace.host_env.permissions import GrantViolation, check_capability
from fastmcp import FastMCP


def register(mcp: FastMCP, ctx_factory) -> None:  # type: ignore[type-arg]
    @mcp.tool(
        name="shell.exec",
        description="Run an allowlisted shell command. Requires shell.exec grant.",
    )
    def shell_exec(cmd: str, cwd: str | None = None, timeout: int = 30) -> dict:
        ctx = ctx_factory()
        try:
            check_capability(ctx.grants, "shell.exec", {"cmd": cmd})
        except GrantViolation as exc:
            ctx.audit("shell.exec", {"cmd": cmd}, outcome="denied", error=str(exc))
            raise
        grant = ctx.grants.get("shell.exec") or {}
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
            ctx.audit("shell.exec", {"cmd": cmd}, outcome="timeout", error="timed out")
            raise
        ctx.audit("shell.exec", {"cmd": cmd}, outcome=outcome, error=error)
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
