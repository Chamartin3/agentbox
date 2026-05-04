"""Tests for MCP resource/env-doc/MCP-policy/host-env tools (Plan 08 Phase 6)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

from agentbox.mcp_server.tools.resources import _require_reason, register
from fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_tool_fn(mcp: FastMCP, name: str):
    async def _fetch():
        return await mcp.get_tool(name)
    return asyncio.run(_fetch()).fn


def _make_mcp() -> FastMCP:
    mcp = FastMCP("test")
    register(mcp)
    return mcp


def _make_ctx(tmp_path: Path):
    ctx = MagicMock()
    ctx.store = MagicMock()
    ctx.loader = MagicMock()
    return ctx


# ---------------------------------------------------------------------------
# _require_reason
# ---------------------------------------------------------------------------


class TestRequireReason:
    def test_valid_reason_returns_none(self):
        assert _require_reason("fix typo") is None

    def test_empty_reason_returns_error(self):
        assert _require_reason("")["error"] == "reason_too_short"

    def test_short_reason_returns_error(self):
        assert _require_reason("ab") is not None

    def test_whitespace_only_returns_error(self):
        assert _require_reason("   ") is not None


# ---------------------------------------------------------------------------
# set_prompt_resources
# ---------------------------------------------------------------------------


class TestSetPromptResources:
    def test_short_reason_returns_error(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path)
        with patch("agentbox.mcp_server.tools.resources.get_context", return_value=ctx):
            mcp = _make_mcp()
            fn = _get_tool_fn(mcp, "set_prompt_resources")
            result = fn("ag1", [], "xy")
        assert result["error"] == "reason_too_short"

    def test_calls_store(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path)
        ctx.store.replace_prompt_bindings.return_value = []
        with patch("agentbox.mcp_server.tools.resources.get_context", return_value=ctx):
            mcp = _make_mcp()
            fn = _get_tool_fn(mcp, "set_prompt_resources")
            result = fn("ag1", [], "add first binding")
        assert result == {"agent_id": "ag1", "bindings": []}
        ctx.store.replace_prompt_bindings.assert_called_once_with("ag1", [], reason="add first binding")


# ---------------------------------------------------------------------------
# preview_prompt
# ---------------------------------------------------------------------------


class TestPreviewPrompt:
    def test_no_bindings_returns_original(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path)
        agent = MagicMock()
        agent.prompt = "Hello {{resource:foo}}"
        ctx.loader.get.return_value = agent
        with patch("agentbox.mcp_server.tools.resources.get_context", return_value=ctx), \
             patch("agentbox.mcp_server.tools.resources.resolve_agent_prompt_bindings", return_value=[]):
            mcp = _make_mcp()
            fn = _get_tool_fn(mcp, "preview_prompt")
            result = fn("ag1")
        assert result["rendered_prompt"] == "Hello {{resource:foo}}"
        assert result["unresolved_markers"] == []

    def test_agent_not_found(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path)
        ctx.loader.get.return_value = None
        with patch("agentbox.mcp_server.tools.resources.get_context", return_value=ctx), \
             patch("agentbox.mcp_server.tools.resources.resolve_agent_prompt_bindings", return_value=[{"marker": "x"}]):
            mcp = _make_mcp()
            fn = _get_tool_fn(mcp, "preview_prompt")
            result = fn("missing")
        assert result["error"] == "agent_not_found"


# ---------------------------------------------------------------------------
# dry_run_workspace_resources
# ---------------------------------------------------------------------------


class TestDryRunWorkspaceResources:
    def test_returns_binding_count(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path)
        fake = [{"dest_path": "docs/ref.md", "resource_id": "r1"}]
        with patch("agentbox.mcp_server.tools.resources.get_context", return_value=ctx), \
             patch("agentbox.mcp_server.tools.resources.resolve_workspace_resources", return_value=fake):
            mcp = _make_mcp()
            fn = _get_tool_fn(mcp, "dry_run_workspace_resources")
            result = fn("ws1")
        assert result["count"] == 1
        assert result["bindings"] == fake


# ---------------------------------------------------------------------------
# set_host_env_grants
# ---------------------------------------------------------------------------


class TestSetHostEnvGrants:
    def test_short_reason_rejected(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path)
        with patch("agentbox.mcp_server.tools.resources.get_context", return_value=ctx):
            mcp = _make_mcp()
            fn = _get_tool_fn(mcp, "set_host_env_grants")
            result = fn("ws1", {}, "xy")
        assert result["error"] == "reason_too_short"

    def test_valid_grants_stored(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path)
        ctx.store.set_workspace_host_env.return_value = {"workspace_id": "ws1"}
        grants = {"fs.read": {"allowed_paths": ["/tmp"]}}
        with patch("agentbox.mcp_server.tools.resources.get_context", return_value=ctx):
            mcp = _make_mcp()
            fn = _get_tool_fn(mcp, "set_host_env_grants")
            result = fn("ws1", grants, "grant fs read")
        ctx.store.set_workspace_host_env.assert_called_once_with("ws1", overrides=grants, changelog="grant fs read")
        assert result == {"workspace_id": "ws1"}


# ---------------------------------------------------------------------------
# list_host_env_calls
# ---------------------------------------------------------------------------


class TestListHostEnvCalls:
    def test_returns_calls(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path)
        ctx.store.list_host_env_calls_for_run.return_value = [
            {"capability": "fs.read", "status": "ok"}
        ] * 3
        with patch("agentbox.mcp_server.tools.resources.get_context", return_value=ctx):
            mcp = _make_mcp()
            fn = _get_tool_fn(mcp, "list_host_env_calls")
            result = fn("run1")
        assert result["total"] == 3
        assert result["run_id"] == "run1"
