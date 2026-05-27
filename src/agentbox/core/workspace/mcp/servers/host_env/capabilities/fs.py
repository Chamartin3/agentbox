"""fs.read, fs.list, fs.write capability tools."""

from __future__ import annotations

from pathlib import Path

from agentbox.core.workspace.host_env.permissions import GrantViolation, check_capability
from fastmcp import FastMCP


def register(mcp: FastMCP, ctx_factory) -> None:  # type: ignore[type-arg]
    @mcp.tool(name="fs.read", description="Read a file. Requires fs.read grant.")
    def fs_read(path: str) -> str:
        ctx = ctx_factory()
        try:
            check_capability(ctx.grants, "fs.read", {"path": path})
        except GrantViolation as exc:
            ctx.audit("fs.read", {"path": path}, outcome="denied", error=str(exc))
            raise
        p = Path(path)
        content = p.read_text(encoding="utf-8", errors="replace")
        ctx.audit("fs.read", {"path": path}, outcome="ok")
        return content

    @mcp.tool(
        name="fs.list", description="List directory entries. Requires fs.list grant."
    )
    def fs_list(path: str) -> list[str]:
        ctx = ctx_factory()
        try:
            check_capability(ctx.grants, "fs.list", {"path": path})
        except GrantViolation as exc:
            ctx.audit("fs.list", {"path": path}, outcome="denied", error=str(exc))
            raise
        entries = sorted(str(e) for e in Path(path).iterdir())
        ctx.audit("fs.list", {"path": path}, outcome="ok")
        return entries

    @mcp.tool(name="fs.write", description="Write a file. Requires fs.write grant.")
    def fs_write(path: str, content: str) -> str:
        ctx = ctx_factory()
        size_hint = len(content.encode())
        try:
            check_capability(
                ctx.grants, "fs.write", {"path": path, "size_hint": size_hint}
            )
        except GrantViolation as exc:
            ctx.audit("fs.write", {"path": path}, outcome="denied", error=str(exc))
            raise
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        ctx.audit("fs.write", {"path": path, "bytes": size_hint}, outcome="ok")
        return f"wrote {size_hint} bytes to {path}"
