"""Tests for MCP resource/env-doc/MCP-policy/host-env tools (Plan 08 Phase 6)."""

from __future__ import annotations

import base64
import io
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from agentbox.mcp.tools.resources import _require_reason, register
from fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_tool_fn(mcp: FastMCP, name: str):
    """Return the underlying Python function for a registered tool by name.

    Accesses FastMCP's _local_provider._components dict which stores
    FunctionTool objects keyed by "tool:<name>@".
    """
    key = f"tool:{name}@"
    tool = mcp._local_provider._components[key]
    return tool.fn


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
        with patch("agentbox.mcp.tools.resources.bindings.get_context", return_value=ctx):
            mcp = _make_mcp()
            fn = _get_tool_fn(mcp, "set_prompt_resources")
            result = fn("ag1", [], "xy")
        assert result["error"] == "reason_too_short"

    def test_calls_store(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path)
        ctx.store.replace_prompt_bindings.return_value = []
        with patch("agentbox.mcp.tools.resources.bindings.get_context", return_value=ctx):
            mcp = _make_mcp()
            fn = _get_tool_fn(mcp, "set_prompt_resources")
            result = fn("ag1", [], "add first binding")
        assert result == {"agent_id": "ag1", "bindings": [], "count": 0}
        ctx.store.replace_prompt_bindings.assert_called_once_with(
            "ag1", [], reason="add first binding"
        )


# ---------------------------------------------------------------------------
# preview_prompt
# ---------------------------------------------------------------------------


class TestPreviewPrompt:
    def test_no_bindings_returns_original(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path)
        agent = MagicMock()
        agent.prompt = "Hello {{resource:foo}}"
        # Agent lookup now goes through ``AgentService.resolve_agent``.
        svc = MagicMock()
        svc.resolve_agent.return_value = agent
        ctx.store.list_prompt_bindings.return_value = []
        with (
            patch("agentbox.mcp.tools.resources.prompts.get_context", return_value=ctx),
            patch(
                "agentbox.mcp.tools.resources.prompts.get_agent_service",
                return_value=svc,
            ),
        ):
            mcp = _make_mcp()
            fn = _get_tool_fn(mcp, "preview_prompt")
            result = fn("ag1")
        # Unresolved markers are stripped from the rendered text and surfaced.
        assert result["rendered_prompt"] == "Hello "
        assert result["unresolved_markers"] == ["foo"]
        assert result["snapshot"] == []
        assert result["total_chars"] == len("Hello ")
        assert result["char_breakdown"][0]["label"] == "prompt template"

    def test_agent_not_found(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path)
        # ``AgentService.resolve_agent`` returning None → agent_not_found.
        svc = MagicMock()
        svc.resolve_agent.return_value = None
        with (
            patch("agentbox.mcp.tools.resources.prompts.get_context", return_value=ctx),
            patch(
                "agentbox.mcp.tools.resources.prompts.get_agent_service",
                return_value=svc,
            ),
        ):
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
        with (
            patch("agentbox.mcp.tools.resources.workspace.get_context", return_value=ctx),
            patch(
                "agentbox.mcp.tools.resources.workspace.resolve_workspace_resources",
                return_value=fake,
            ),
        ):
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
        with patch("agentbox.mcp.tools.resources.workspace.get_context", return_value=ctx):
            mcp = _make_mcp()
            fn = _get_tool_fn(mcp, "set_host_env_grants")
            result = fn("ws1", {}, "xy")
        assert result["error"] == "reason_too_short"

    def test_valid_grants_stored(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path)
        ctx.store.set_workspace_host_env.return_value = {"workspace_id": "ws1"}
        grants = {"fs.read": {"allowed_paths": ["/tmp"]}}
        with patch("agentbox.mcp.tools.resources.workspace.get_context", return_value=ctx):
            mcp = _make_mcp()
            fn = _get_tool_fn(mcp, "set_host_env_grants")
            result = fn("ws1", grants, "grant fs read")
        ctx.store.set_workspace_host_env.assert_called_once_with(
            "ws1", profile_id=None, overrides=grants, changelog="grant fs read"
        )
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
        with patch("agentbox.mcp.tools.resources.workspace.get_context", return_value=ctx):
            mcp = _make_mcp()
            fn = _get_tool_fn(mcp, "list_host_env_calls")
            result = fn("run1")
        assert result["total"] == 3
        assert result["run_id"] == "run1"


# ---------------------------------------------------------------------------
# create_repo_resource — zip routing for folder/skill
# ---------------------------------------------------------------------------


def _make_zip_bytes(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, raw in files.items():
            zf.writestr(path, raw)
    return buf.getvalue()


class TestCreateRepoResourceZipRouting:
    def test_skill_requires_zip_bytes(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path)
        ctx.store.create_repo_resource.return_value = {"id": "r1", "type": "skill"}
        with patch("agentbox.mcp.tools.resources.repo.get_context", return_value=ctx):
            mcp = _make_mcp()
            fn = _get_tool_fn(mcp, "create_repo_resource")
            result = fn(
                slug="my-skill",
                type="skill",
                display_name="My Skill",
                content_base64=base64.b64encode(b"not a zip").decode(),
                changelog="initial upload",
            )
        assert result["error"] == "invalid_payload"

    def test_document_rejects_zip_bytes(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path)
        ctx.store.create_repo_resource.return_value = {"id": "r1", "type": "document"}
        zip_b64 = base64.b64encode(_make_zip_bytes({"a.md": b"hi"})).decode()
        with patch("agentbox.mcp.tools.resources.repo.get_context", return_value=ctx):
            mcp = _make_mcp()
            fn = _get_tool_fn(mcp, "create_repo_resource")
            result = fn(
                slug="doc1",
                type="document",
                display_name="Doc",
                content_base64=zip_b64,
                changelog="initial upload",
            )
        assert result["error"] == "invalid_payload"

    def test_skill_with_zip_routes_to_zip_importer(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path)
        ctx.store.create_repo_resource.return_value = {"id": "r1", "type": "skill"}
        ctx.store.import_repo_version.return_value = {"id": "v1"}
        zip_b64 = base64.b64encode(
            _make_zip_bytes(
                {
                    "SKILL.md": b"---\nname: test\ndescription: x\n---\n# Test\n",
                    "references/r1.md": b"# Ref",
                }
            )
        ).decode()
        with patch("agentbox.mcp.tools.resources.repo.get_context", return_value=ctx):
            mcp = _make_mcp()
            fn = _get_tool_fn(mcp, "create_repo_resource")
            result = fn(
                slug="test-skill",
                type="skill",
                display_name="Test Skill",
                content_base64=zip_b64,
                changelog="initial upload",
            )
        assert "error" not in result
        assert result["resource"]["id"] == "r1"
        assert result["version"]["id"] == "v1"
        ctx.store.import_repo_version.assert_called_once()


# ---------------------------------------------------------------------------
# create_repo_resource_from_files
# ---------------------------------------------------------------------------


class TestCreateRepoResourceFromFiles:
    def test_rejects_non_skill_or_folder(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path)
        with patch("agentbox.mcp.tools.resources.importers.get_context", return_value=ctx):
            mcp = _make_mcp()
            fn = _get_tool_fn(mcp, "create_repo_resource_from_files")
            result = fn(
                slug="x",
                type="document",
                display_name="X",
                files=[{"path": "a.md", "content": "hi"}],
                changelog="initial",
            )
        assert result["error"] == "invalid_type"

    def test_rejects_short_changelog(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path)
        with patch("agentbox.mcp.tools.resources.importers.get_context", return_value=ctx):
            mcp = _make_mcp()
            fn = _get_tool_fn(mcp, "create_repo_resource_from_files")
            result = fn(
                slug="x",
                type="skill",
                display_name="X",
                files=[{"path": "SKILL.md", "content": "x"}],
                changelog="ab",
            )
        assert result["error"] == "reason_too_short"

    def test_rejects_empty_files(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path)
        with patch("agentbox.mcp.tools.resources.importers.get_context", return_value=ctx):
            mcp = _make_mcp()
            fn = _get_tool_fn(mcp, "create_repo_resource_from_files")
            result = fn(
                slug="x",
                type="skill",
                display_name="X",
                files=[],
                changelog="initial upload",
            )
        assert result["error"] == "invalid_request"

    def test_rejects_unsafe_path(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path)
        with patch("agentbox.mcp.tools.resources.importers.get_context", return_value=ctx):
            mcp = _make_mcp()
            fn = _get_tool_fn(mcp, "create_repo_resource_from_files")
            result = fn(
                slug="x",
                type="skill",
                display_name="X",
                files=[{"path": "../escape.md", "content": "x"}],
                changelog="initial upload",
            )
        assert result["error"] == "invalid_request"
        assert "unsafe" in result["detail"]

    def test_rejects_duplicate_path(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path)
        with patch("agentbox.mcp.tools.resources.importers.get_context", return_value=ctx):
            mcp = _make_mcp()
            fn = _get_tool_fn(mcp, "create_repo_resource_from_files")
            result = fn(
                slug="x",
                type="skill",
                display_name="X",
                files=[
                    {"path": "SKILL.md", "content": "a"},
                    {"path": "SKILL.md", "content": "b"},
                ],
                changelog="initial upload",
            )
        assert result["error"] == "invalid_request"
        assert "duplicate" in result["detail"]

    def test_skill_requires_skill_md(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path)
        with patch("agentbox.mcp.tools.resources.importers.get_context", return_value=ctx):
            mcp = _make_mcp()
            fn = _get_tool_fn(mcp, "create_repo_resource_from_files")
            result = fn(
                slug="x",
                type="skill",
                display_name="X",
                files=[{"path": "references/r.md", "content": "hi"}],
                changelog="initial upload",
            )
        assert result["error"] == "invalid_request"
        assert "SKILL.md" in result["detail"]

    def test_happy_path_creates_resource_and_version(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path)
        ctx.store.create_repo_resource.return_value = {"id": "r1", "type": "skill"}
        ctx.store.import_repo_version.return_value = {"id": "v1"}
        with patch("agentbox.mcp.tools.resources.importers.get_context", return_value=ctx):
            mcp = _make_mcp()
            fn = _get_tool_fn(mcp, "create_repo_resource_from_files")
            result = fn(
                slug="my-skill",
                type="skill",
                display_name="My Skill",
                files=[
                    {
                        "path": "SKILL.md",
                        "content": "---\nname: my_skill\ndescription: x\n---\n# My Skill\n",
                    },
                    {"path": "references/clustering.md", "content": "# Clustering"},
                ],
                changelog="initial upload",
            )
        assert "error" not in result
        assert result["resource"]["id"] == "r1"
        assert result["version"]["id"] == "v1"
        assert result["file_count"] == 2
        ctx.store.import_repo_version.assert_called_once()
