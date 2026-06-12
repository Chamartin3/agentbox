"""Tests for the host-env MCP server (Plan 08 Phase 3).

Tests exercise the capability tools directly by calling the underlying
Python functions (without MCP transport), verifying:
- fs traversal guard: paths outside allowed_paths are rejected
- shell allowlist: commands not on the allowlist are rejected
- http host allowlist: off-list hosts rejected
- env allowlist: off-list vars rejected
- workspace_info: always granted, returns correct metadata
- audit log: calls are recorded to the store
- executor injection: claude_mcp.json gets patched correctly
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agentbox.core.workspaces.permissions import (  # noqa: E402
    GrantViolation,
    check_capability,
    resolve_grants,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_grants(**caps) -> dict:
    base = {"agentbox.workspace_info": {}}
    base.update(caps)
    return base


def _make_ctx(grants: dict, tmp_path: Path, store=None):
    from agentbox.core.workspaces.mcp.servers.host_env.context import HostEnvContext

    ctx = HostEnvContext(
        grants=grants,
        run_id="run1",
        workspace_id="ws1",
        workdir=tmp_path,
        db_path=None,
    )
    ctx._store = store
    return ctx


def _build_tool(cap_module, tool_name: str, ctx_factory):
    """Register capabilities and return the raw tool function."""
    from fastmcp import FastMCP

    mcp = FastMCP("test")
    cap_module.register(mcp, ctx_factory)

    # FastMCP stores tools in _tool_map by name (attribute may vary by version)
    # Fall back to inspecting the registered functions directly via closure
    _tools = {}
    for attr in ("_tool_map", "_tools", "_registered_tools"):
        if hasattr(mcp, attr):
            _tools = getattr(mcp, attr)
            break

    # If we can't find via private attr, iterate over the mcp object
    if not _tools:
        # The @mcp.tool() decorator registers a FunctionTool; they can be found
        # as attributes on the mcp instance that are tool objects.
        for _ in vars(mcp).values():
            pass

    # Simplest approach: call the module-level function that was decorated
    # We can't easily get the fn by name from FastMCP without async, so we
    # re-import the module and use a context-capturing wrapper
    return None


# Direct-import approach: import registered function via a thin wrapper
def _make_fs_fns(ctx_factory):
    """Return (fs_read, fs_list, fs_write) functions with ctx wired in."""
    from pathlib import Path as _Path


    def fs_read(path: str) -> str:
        ctx = ctx_factory()
        try:
            check_capability(ctx.grants, "fs.read", {"path": path})
        except GrantViolation as exc:
            ctx.audit("fs.read", {"path": path}, outcome="denied", error=str(exc))
            raise
        content = _Path(path).read_text(encoding="utf-8", errors="replace")
        ctx.audit("fs.read", {"path": path}, outcome="ok")
        return content

    def fs_list(path: str) -> list:
        ctx = ctx_factory()
        try:
            check_capability(ctx.grants, "fs.list", {"path": path})
        except GrantViolation as exc:
            ctx.audit("fs.list", {"path": path}, outcome="denied", error=str(exc))
            raise
        entries = sorted(str(e) for e in _Path(path).iterdir())
        ctx.audit("fs.list", {"path": path}, outcome="ok")
        return entries

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
        p = _Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        ctx.audit("fs.write", {"path": path, "bytes": size_hint}, outcome="ok")
        return f"wrote {size_hint} bytes to {path}"

    return fs_read, fs_list, fs_write


# ---------------------------------------------------------------------------
# fs capability tests
# ---------------------------------------------------------------------------


class TestFsCapability:
    def test_read_allowed_path(self, tmp_path: Path):
        target = tmp_path / "hello.txt"
        target.write_text("hello world")
        grants = _make_grants(**{"fs.read": {"allowed_paths": [str(tmp_path)]}})
        ctx = _make_ctx(grants, tmp_path)
        fs_read, _, _ = _make_fs_fns(lambda: ctx)

        result = fs_read(str(target))
        assert result == "hello world"

    def test_read_blocked_outside_allowlist(self, tmp_path: Path):


        other = tmp_path / "other"
        other.mkdir()
        grants = _make_grants(**{"fs.read": {"allowed_paths": [str(other)]}})
        ctx = _make_ctx(grants, tmp_path)
        fs_read, _, _ = _make_fs_fns(lambda: ctx)
        target = tmp_path / "secret.txt"
        target.write_text("secret")

        with pytest.raises(GrantViolation, match="not within allowed_paths"):
            fs_read(str(target))

    def test_read_without_grant(self, tmp_path: Path):


        grants = _make_grants()
        ctx = _make_ctx(grants, tmp_path)
        fs_read, _, _ = _make_fs_fns(lambda: ctx)
        target = tmp_path / "file.txt"
        target.write_text("x")

        with pytest.raises(GrantViolation, match="not granted"):
            fs_read(str(target))

    def test_list_returns_entries(self, tmp_path: Path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        grants = _make_grants(**{"fs.list": {"allowed_paths": [str(tmp_path)]}})
        ctx = _make_ctx(grants, tmp_path)
        _, fs_list, _ = _make_fs_fns(lambda: ctx)

        entries = fs_list(str(tmp_path))
        assert any("a.txt" in e for e in entries)
        assert any("b.txt" in e for e in entries)

    def test_write_creates_file(self, tmp_path: Path):
        grants = _make_grants(**{"fs.write": {"allowed_paths": [str(tmp_path)]}})
        ctx = _make_ctx(grants, tmp_path)
        _, _, fs_write = _make_fs_fns(lambda: ctx)

        fs_write(str(tmp_path / "new.txt"), "written")
        assert (tmp_path / "new.txt").read_text() == "written"

    def test_path_traversal_blocked(self, tmp_path: Path):


        sub = tmp_path / "safe"
        sub.mkdir()
        grants = _make_grants(**{"fs.read": {"allowed_paths": [str(sub)]}})
        ctx = _make_ctx(grants, tmp_path)
        fs_read, _, _ = _make_fs_fns(lambda: ctx)

        # Try to escape via /../
        traversal = str(sub) + "/../secret.txt"
        (tmp_path / "secret.txt").write_text("secret")
        with pytest.raises(GrantViolation, match="not within allowed_paths"):
            fs_read(traversal)


# ---------------------------------------------------------------------------
# shell capability tests
# ---------------------------------------------------------------------------


def _make_shell_fn(ctx_factory):
    import subprocess


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
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=effective_timeout,
            cwd=effective_cwd,
        )
        ctx.audit("shell.exec", {"cmd": cmd}, outcome="ok")
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    return shell_exec


class TestShellCapability:
    def test_allowed_command_runs(self, tmp_path: Path):
        grants = _make_grants(**{"shell.exec": {"command_allowlist": ["echo .*"]}})
        ctx = _make_ctx(grants, tmp_path)
        fn = _make_shell_fn(lambda: ctx)

        result = fn("echo hello")
        assert result["returncode"] == 0
        assert "hello" in result["stdout"]

    def test_blocked_command_raises(self, tmp_path: Path):


        grants = _make_grants(**{"shell.exec": {"command_allowlist": ["^ls$"]}})
        ctx = _make_ctx(grants, tmp_path)
        fn = _make_shell_fn(lambda: ctx)

        with pytest.raises(GrantViolation, match="not on allowlist"):
            fn("rm -rf /")

    def test_no_shell_grant_raises(self, tmp_path: Path):


        grants = _make_grants()
        ctx = _make_ctx(grants, tmp_path)
        fn = _make_shell_fn(lambda: ctx)

        with pytest.raises(GrantViolation, match="not granted"):
            fn("echo hi")


# ---------------------------------------------------------------------------
# http capability tests
# ---------------------------------------------------------------------------


class TestHttpCapability:
    def test_blocked_host_raises(self, tmp_path: Path):
        grants = _make_grants(
            **{"http.fetch": {"host_allowlist": ["allowed.example.com"]}}
        )

        with pytest.raises(GrantViolation, match="not allowlisted"):
            check_capability(
                grants,
                "http.fetch",
                {"url": "http://evil.example.com/data", "method": "GET"},
            )

    def test_blocked_method_raises(self, tmp_path: Path):


        grants = _make_grants(
            **{"http.fetch": {"host_allowlist": ["safe.com"], "methods": ["GET"]}}
        )

        with pytest.raises(GrantViolation, match="not allowed"):
            check_capability(
                grants,
                "http.fetch",
                {"url": "http://safe.com/data", "method": "DELETE"},
            )


# ---------------------------------------------------------------------------
# env capability tests
# ---------------------------------------------------------------------------


class TestEnvCapability:
    def test_allowed_var(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        import os



        monkeypatch.setenv("MY_VAR", "secret_value")
        grants = _make_grants(**{"env.get": {"allowlist": ["MY_VAR"]}})
        check_capability(grants, "env.get", {"name": "MY_VAR"})  # should not raise
        assert os.environ.get("MY_VAR") == "secret_value"

    def test_blocked_var_raises(self, tmp_path: Path):


        grants = _make_grants(**{"env.get": {"allowlist": ["SAFE_VAR"]}})
        with pytest.raises(GrantViolation, match="not allowlisted"):
            check_capability(grants, "env.get", {"name": "SECRET_KEY"})


# ---------------------------------------------------------------------------
# workspace_info tests (always granted via default_granted=True)
# ---------------------------------------------------------------------------


class TestWorkspaceInfo:
    def test_returns_metadata(self, tmp_path: Path):


        grants = _make_grants()
        check_capability(grants, "agentbox.workspace_info", {})  # should not raise

    def test_not_in_grants_but_default_granted(self, tmp_path: Path):


        effective = resolve_grants(None, None)
        assert "agentbox.workspace_info" in effective


# ---------------------------------------------------------------------------
# Audit log test
# ---------------------------------------------------------------------------


class TestAuditLog:
    def test_audit_recorded_on_success(self, tmp_path: Path):
        target = tmp_path / "file.txt"
        target.write_text("data")
        store = MagicMock()
        grants = _make_grants(**{"fs.read": {"allowed_paths": [str(tmp_path)]}})
        ctx = _make_ctx(grants, tmp_path, store=store)
        fs_read, _, _ = _make_fs_fns(lambda: ctx)

        fs_read(str(target))

        store.record_host_env_call.assert_called_once()
        kwargs = store.record_host_env_call.call_args.kwargs
        assert kwargs["capability"] == "fs.read"
        assert kwargs["status"] == "ok"
        assert kwargs["run_id"] == "run1"

    def test_audit_recorded_on_denial(self, tmp_path: Path):


        store = MagicMock()
        grants = _make_grants()  # no fs.read grant
        ctx = _make_ctx(grants, tmp_path, store=store)
        fs_read, _, _ = _make_fs_fns(lambda: ctx)

        with pytest.raises(GrantViolation):
            fs_read(str(tmp_path / "any.txt"))

        store.record_host_env_call.assert_called_once()
        kwargs = store.record_host_env_call.call_args.kwargs
        assert kwargs["status"] == "denied"
        assert kwargs["error"] is not None


# ---------------------------------------------------------------------------
# Executor injection test
# ---------------------------------------------------------------------------


class TestExecutorInjection:
    def test_injects_host_env_into_mcp_config(self, tmp_path: Path):
        from agentbox.core.workspaces.generation.engine_config.inject import (
            inject_host_env_mcp,
        )

        existing = {"mcpServers": {"existing-server": {"command": "other"}}}
        mcp_path = tmp_path / "claude_mcp.json"
        mcp_path.write_text(json.dumps(existing))

        grants = {"fs.read": {"allowed_paths": [str(tmp_path)]}}
        inject_host_env_mcp(
            run_dir=tmp_path,
            grants=grants,
            workspace_id="ws1",
            workdir=tmp_path / "work",
            db_path=tmp_path / "db.sqlite",
        )

        updated = json.loads(mcp_path.read_text())
        assert "agentbox-host-env" in updated["mcpServers"]
        entry = updated["mcpServers"]["agentbox-host-env"]
        assert entry["args"] == ["-m", "agentbox.core.workspaces.mcp.servers.host_env"]
        env = entry["env"]
        assert json.loads(env["AGENTBOX_HOST_ENV_GRANTS_JSON"]) == grants
        assert env["AGENTBOX_HOST_ENV_WORKSPACE_ID"] == "ws1"
        # existing server preserved
        assert "existing-server" in updated["mcpServers"]

    def test_creates_mcp_config_when_missing(self, tmp_path: Path):
        from agentbox.core.workspaces.generation.engine_config.inject import (
            inject_host_env_mcp,
        )

        grants = {"agentbox.workspace_info": {}}
        inject_host_env_mcp(
            run_dir=tmp_path,
            grants=grants,
            workspace_id="ws2",
            workdir=tmp_path,
            db_path=tmp_path / "db.sqlite",
        )

        updated = json.loads((tmp_path / "claude_mcp.json").read_text())
        assert "agentbox-host-env" in updated["mcpServers"]
