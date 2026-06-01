"""environment_mcp server — one MCP surface for every backend.

Only the tools listed in the per-agent ``agent_tool_grants`` set are
registered; ungranted tools simply aren't visible to the model. This
keeps small models from looping on ``not_granted`` errors.

Tool names are prefixed ``box.`` so backends see a single namespace.
``box.web.search`` is wired but returns ``{"error": "not_configured"}``
unless ``AGENTBOX_WEB_SEARCH_PROVIDER`` is set.
"""

from __future__ import annotations

import logging
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from agentbox.core.tools.environment_mcp.context import EnvironmentMcpContext
from fastmcp import FastMCP

logger = logging.getLogger(__name__)

def build_server(ctx: EnvironmentMcpContext | None = None) -> FastMCP:
    if ctx is None:
        ctx = EnvironmentMcpContext.from_env()

    mcp = FastMCP(
        name="environment_mcp",
        instructions=(
            "Native environment tools (fs, shell, git, http, env vars, "
            "workspace info, web search). Only the tools your agent has "
            "been granted are visible here."
        ),
    )

    _register_all(mcp, ctx)
    return mcp


def _audited(ctx: EnvironmentMcpContext, name: str, fn: Callable[..., Any]):
    """Wrap ``fn`` to audit calls and surface exceptions as JSON to the model."""

    def wrapped(*args: Any, **kwargs: Any) -> Any:
        try:
            out = fn(*args, **kwargs)
            ctx.audit(name, kwargs or None, "ok")
            return out
        except Exception as exc:  # ponytail: surface as JSON to the model
            ctx.audit(name, kwargs or None, "error", str(exc))
            return {"error": str(exc)}

    wrapped.__name__ = name.replace(".", "_")
    return wrapped


def _register_all(mcp: FastMCP, ctx: EnvironmentMcpContext) -> None:
    """Register only the tools that ``ctx.grants`` permits."""

    def _grant(name: str) -> bool:
        return ctx.is_granted(name)

    def _resolve(path: str) -> Path:
        """Anchor relative paths to the workspace; leave absolute paths alone."""
        p = Path(path)
        return p if p.is_absolute() else (ctx.workdir / p)

    if _grant("box.fs.read"):
        @mcp.tool(
            name="box.fs.read",
            description=(
                "Read a file as text. Paths are workspace-relative unless "
                "absolute; e.g. 'README.md' reads $WORKDIR/README.md."
            ),
        )
        def _fs_read(path: str) -> Any:
            def _impl(path: str) -> dict:
                target = _resolve(path)
                return {
                    "path": str(target),
                    "content": target.read_text(encoding="utf-8", errors="replace"),
                }

            return _audited(ctx, "box.fs.read", _impl)(path=path)

    if _grant("box.fs.list"):
        @mcp.tool(
            name="box.fs.list",
            description=(
                "List directory entries. Defaults to the workspace root; "
                "relative paths resolve against the workspace."
            ),
        )
        def _fs_list(path: str = ".") -> Any:
            def _impl(path: str) -> dict:
                target = _resolve(path)
                entries = []
                for e in sorted(target.iterdir()):
                    entries.append(
                        {"path": str(e), "type": "dir" if e.is_dir() else "file"}
                    )
                return {"entries": entries}

            return _audited(ctx, "box.fs.list", _impl)(path=path)

    if _grant("box.fs.write"):
        @mcp.tool(
            name="box.fs.write",
            description=(
                "Write text to a file. Paths are workspace-relative unless "
                "absolute."
            ),
        )
        def _fs_write(path: str, content: str) -> Any:
            def _impl(path: str, content: str) -> dict:
                target = _resolve(path)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                return {"path": str(target), "bytes": len(content.encode())}

            return _audited(ctx, "box.fs.write", _impl)(path=path, content=content)

    if _grant("box.shell.exec"):
        @mcp.tool(name="box.shell.exec", description="Run a shell command.")
        def _shell_exec(cmd: str, cwd: str | None = None, timeout: int = 30) -> Any:
            def _impl(cmd: str, cwd: str | None, timeout: int) -> dict:
                r = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=min(timeout, 60),
                    cwd=cwd or str(ctx.workdir),
                )
                return {
                    "exit_code": r.returncode,
                    "stdout": r.stdout[:65536],
                    "stderr": r.stderr[:65536],
                }

            return _audited(ctx, "box.shell.exec", _impl)(
                cmd=cmd, cwd=cwd, timeout=timeout
            )

    if _grant("box.git.status"):
        @mcp.tool(name="box.git.status", description="git status --porcelain in a repo.")
        def _git_status(path: str | None = None) -> Any:
            def _impl(path: str | None) -> dict:
                cwd = path or str(ctx.workdir)
                r = subprocess.run(
                    ["git", "status", "--porcelain=v1"],
                    capture_output=True,
                    text=True,
                    cwd=cwd,
                    timeout=5,
                )
                if r.returncode != 0:
                    raise RuntimeError(r.stderr.strip() or "git status failed")
                return {"raw": r.stdout}

            return _audited(ctx, "box.git.status", _impl)(path=path)

    if _grant("box.http.fetch"):
        @mcp.tool(name="box.http.fetch", description="HTTP GET/HEAD a URL.")
        def _http_fetch(url: str, method: str = "GET", timeout: int = 10) -> Any:
            def _impl(url: str, method: str, timeout: int) -> dict:
                m = method.upper()
                if m not in {"GET", "HEAD"}:
                    raise ValueError("only GET/HEAD supported")
                req = urllib.request.Request(
                    url, method=m, headers={"User-Agent": "environment_mcp/1"}
                )
                try:
                    with urllib.request.urlopen(req, timeout=min(timeout, 30)) as resp:
                        body = resp.read(262144).decode(errors="replace")
                        return {
                            "status": resp.status,
                            "headers": dict(resp.headers),
                            "body": body,
                        }
                except urllib.error.HTTPError as exc:
                    return {"status": exc.code, "body": exc.read(262144).decode(errors="replace")}

            return _audited(ctx, "box.http.fetch", _impl)(
                url=url, method=method, timeout=timeout
            )

    if _grant("box.env.get"):
        @mcp.tool(name="box.env.get", description="Read an environment variable.")
        def _env_get(name: str) -> Any:
            return _audited(
                ctx,
                "box.env.get",
                lambda name: {"name": name, "value": os.environ.get(name)},
            )(name=name)

    if _grant("box.workspace_info"):
        @mcp.tool(name="box.workspace_info", description="Workspace metadata.")
        def _workspace_info() -> Any:
            def _impl() -> dict:
                wd = ctx.workdir
                claude_md = wd / "CLAUDE.md"
                return {
                    "workspace_id": ctx.workspace_id,
                    "agent_id": ctx.agent_id,
                    "run_id": ctx.run_id,
                    "workdir": str(wd),
                    "claude_md_present": claude_md.exists(),
                }

            return _audited(ctx, "box.workspace_info", _impl)()

    if _grant("box.web.search"):
        @mcp.tool(name="box.web.search", description="Search the web (provider-backed).")
        def _web_search(query: str, limit: int = 5) -> Any:
            def _impl(query: str, limit: int) -> dict:
                provider = os.environ.get("AGENTBOX_WEB_SEARCH_PROVIDER", "").strip()
                if not provider:
                    return {"error": "not_configured"}
                # ponytail: stub — single provider wired when a row needs it.
                return {"error": f"provider {provider!r} not implemented"}

            return _audited(ctx, "box.web.search", _impl)(
                query=query, limit=min(limit, 10)
            )


def demo() -> None:
    """Self-check: only granted tools register; ungranted ones are absent."""
    import asyncio

    granted = {"box.fs.read", "box.workspace_info", "box.web.search"}
    ctx = EnvironmentMcpContext(
        grants=frozenset(granted),
        agent_id="a",
        run_id="r",
        workspace_id="w",
        workdir=Path("/tmp"),
        db_path=None,
    )
    mcp = build_server(ctx)
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert names == granted, f"unexpected tool set: {names}"

    empty_ctx = EnvironmentMcpContext(
        grants=frozenset(), agent_id="a", run_id="r", workspace_id="w",
        workdir=Path("/tmp"), db_path=None,
    )
    empty_names = {t.name for t in asyncio.run(build_server(empty_ctx).list_tools())}
    assert empty_names == set(), f"empty grants should expose nothing: {empty_names}"
    print("ok: registered", sorted(names))


if __name__ == "__main__":
    demo()
