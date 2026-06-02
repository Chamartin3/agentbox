"""git.status / git.log / git.diff / git.show capability tools."""

from __future__ import annotations

import subprocess

from agentbox.core.workspace.permissions import GrantViolation, check_capability
from fastmcp import FastMCP


def _run_git(args: list[str], cwd: str) -> str:
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {args[0]} failed")
    return result.stdout


def register(mcp: FastMCP, ctx_factory) -> None:  # type: ignore[type-arg]
    @mcp.tool(
        name="git.status",
        description="git status in a repo directory. Requires git.status grant.",
    )
    def git_status(path: str) -> str:
        ctx = ctx_factory()
        try:
            check_capability(ctx.grants, "git.status", {"path": path})
        except GrantViolation as exc:
            ctx.audit("git.status", {"path": path}, outcome="denied", error=str(exc))
            raise
        out = _run_git(["status"], cwd=path)
        ctx.audit("git.status", {"path": path}, outcome="ok")
        return out

    @mcp.tool(
        name="git.log",
        description="git log in a repo directory. Requires git.log grant.",
    )
    def git_log(path: str, n: int = 20) -> str:
        ctx = ctx_factory()
        try:
            check_capability(ctx.grants, "git.log", {"path": path})
        except GrantViolation as exc:
            ctx.audit("git.log", {"path": path}, outcome="denied", error=str(exc))
            raise
        out = _run_git(["log", "--oneline", f"-{n}"], cwd=path)
        ctx.audit("git.log", {"path": path}, outcome="ok")
        return out

    @mcp.tool(
        name="git.diff",
        description="git diff in a repo directory. Requires git.diff grant.",
    )
    def git_diff(path: str, ref: str | None = None) -> str:
        ctx = ctx_factory()
        try:
            check_capability(ctx.grants, "git.diff", {"path": path})
        except GrantViolation as exc:
            ctx.audit("git.diff", {"path": path}, outcome="denied", error=str(exc))
            raise
        args = ["diff"] + ([ref] if ref else [])
        out = _run_git(args, cwd=path)
        ctx.audit("git.diff", {"path": path}, outcome="ok")
        return out
