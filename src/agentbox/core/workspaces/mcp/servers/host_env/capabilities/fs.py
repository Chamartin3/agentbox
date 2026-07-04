"""fs.read, fs.list, fs.write capability tools."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from agentbox.core.tools.canonical import CanonicalTool
from agentbox.core.workspaces.mcp.servers.host_env.context import HostEnvContext
from agentbox.core.workspaces.permissions import GrantViolation, check_capability
from fastmcp import FastMCP


def register(mcp: FastMCP, ctx_factory: Callable[[], HostEnvContext]) -> None:
    @mcp.tool(
        name=CanonicalTool.FS_READ.value,
        description="Read a file. Requires fs.read grant.",
    )
    def fs_read(path: str) -> str:
        ctx = ctx_factory()
        try:
            check_capability(ctx.grants, CanonicalTool.FS_READ, {"path": path})
        except GrantViolation as exc:
            ctx.audit(CanonicalTool.FS_READ, {"path": path}, outcome="denied", error=str(exc))
            raise
        p = Path(path)
        content = p.read_text(encoding="utf-8", errors="replace")
        ctx.audit(CanonicalTool.FS_READ, {"path": path}, outcome="ok")
        return content

    @mcp.tool(
        name=CanonicalTool.FS_LIST.value,
        description="List directory entries. Requires fs.list grant.",
    )
    def fs_list(path: str) -> list[str]:
        ctx = ctx_factory()
        try:
            check_capability(ctx.grants, CanonicalTool.FS_LIST, {"path": path})
        except GrantViolation as exc:
            ctx.audit(CanonicalTool.FS_LIST, {"path": path}, outcome="denied", error=str(exc))
            raise
        entries = sorted(str(e) for e in Path(path).iterdir())
        ctx.audit(CanonicalTool.FS_LIST, {"path": path}, outcome="ok")
        return entries

    @mcp.tool(
        name=CanonicalTool.FS_WRITE.value,
        description="Write a file. Requires fs.write grant.",
    )
    def fs_write(path: str, content: str) -> str:
        ctx = ctx_factory()
        size_hint = len(content.encode())
        try:
            check_capability(
                ctx.grants, CanonicalTool.FS_WRITE, {"path": path, "size_hint": size_hint}
            )
        except GrantViolation as exc:
            ctx.audit(CanonicalTool.FS_WRITE, {"path": path}, outcome="denied", error=str(exc))
            raise
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        ctx.audit(CanonicalTool.FS_WRITE, {"path": path, "bytes": size_hint}, outcome="ok")
        return f"wrote {size_hint} bytes to {path}"
