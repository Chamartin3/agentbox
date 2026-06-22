"""Tests for workspace prep helpers (previously in execution/prepare/envdoc).

Covers the helper functions now consolidated into workspaces/prep.py:
- resolve_workspace_resources: returns hydrated binding dicts
- resolve_agent_prompt_bindings: returns hydrated binding dicts
- render_env_doc: writes CLAUDE.md + AGENTS.md and returns snapshot entries
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_store(
    *,
    workspace_bindings: list[dict] | None = None,
    prompt_bindings: list[dict] | None = None,
    resource: dict | None = None,
    active_version: dict | None = None,
    version: dict | None = None,
    blobs: list[dict] | None = None,
    active_env_doc: dict | None = None,
) -> MagicMock:
    store = MagicMock()
    store.list_workspace_file_bindings.return_value = workspace_bindings or []
    store.list_prompt_bindings.return_value = prompt_bindings or []
    store.get_repo_resource.return_value = resource
    store.get_active_repo_version.return_value = active_version
    store.get_repo_version.return_value = version or {"content_hash": "abc123"}
    store.iter_repo_blobs.return_value = iter(blobs or [])
    store.get_active_env_doc.return_value = active_env_doc
    return store


def _simple_binding(
    bid: str = "b1",
    resource_id: str = "r1",
    target_path: str | None = None,
    mode: str = "copy",
    on_conflict: str = "error",
) -> dict:
    return {
        "id": bid,
        "resource_id": resource_id,
        "target_path": target_path,
        "materialize_mode": mode,
        "on_conflict": on_conflict,
        "pinned_version_id": None,
    }


def _simple_prompt_binding(bid: str = "pb1", resource_id: str = "r1") -> dict:
    return {
        "id": bid,
        "resource_id": resource_id,
        "marker": "docs",
        "mode": "inline",
        "pinned_version_id": None,
        "required": 1,
    }


# ---------------------------------------------------------------------------
# resolve_workspace_resources
# ---------------------------------------------------------------------------


class TestResolveWorkspaceResources:
    def test_ephemeral_workspace_returns_empty(self):
        from agentbox.core.workspaces.prep import resolve_workspace_resources

        store = _make_store()
        assert resolve_workspace_resources(store, "<ephemeral>") == []
        store.list_workspace_file_bindings.assert_not_called()

    def test_none_workspace_returns_empty(self):
        from agentbox.core.workspaces.prep import resolve_workspace_resources

        store = _make_store()
        assert resolve_workspace_resources(store, "") == []

    def test_no_bindings_returns_empty(self):
        from agentbox.core.workspaces.prep import resolve_workspace_resources

        store = _make_store(workspace_bindings=[])
        result = resolve_workspace_resources(store, "ws1")
        assert result == []

    def test_hydrates_binding_with_active_version(self):
        from agentbox.core.workspaces.prep import resolve_workspace_resources

        binding = _simple_binding(target_path="docs/")
        resource = {
            "id": "r1",
            "slug": "my-doc",
            "type": "document",
            "display_name": "my-doc",
        }
        active_v = {"id": "v1"}
        version = {"content_hash": "deadbeef"}
        blobs = [{"path": "README.md", "content": b"hello"}]
        store = _make_store(
            workspace_bindings=[binding],
            resource=resource,
            active_version=active_v,
            version=version,
            blobs=blobs,
        )

        result = resolve_workspace_resources(store, "ws1")

        assert len(result) == 1
        r = result[0]
        assert r["binding_id"] == "b1"
        assert r["resource_id"] == "r1"
        assert r["version_id"] == "v1"
        assert r["content_hash"] == "deadbeef"
        assert r["type"] == "document"
        assert r["target_path"] == "docs/"
        assert r["blobs"] == blobs

    def test_skips_binding_with_missing_resource(self):
        from agentbox.core.workspaces.prep import resolve_workspace_resources

        store = _make_store(workspace_bindings=[_simple_binding()], resource=None)
        result = resolve_workspace_resources(store, "ws1")
        assert result == []

    def test_skips_binding_with_no_active_version(self):
        from agentbox.core.workspaces.prep import resolve_workspace_resources

        resource = {"id": "r1", "slug": "x", "type": "document", "display_name": "x"}
        store = _make_store(
            workspace_bindings=[_simple_binding()],
            resource=resource,
            active_version=None,
        )
        result = resolve_workspace_resources(store, "ws1")
        assert result == []

    def test_uses_pinned_version_id(self):
        from agentbox.core.workspaces.prep import resolve_workspace_resources

        binding = {**_simple_binding(), "pinned_version_id": "pinned-v99"}
        resource = {"id": "r1", "slug": "x", "type": "document", "display_name": "x"}
        version = {"content_hash": "pinnedhash"}
        store = _make_store(
            workspace_bindings=[binding],
            resource=resource,
            version=version,
            blobs=[],
        )

        result = resolve_workspace_resources(store, "ws1")
        assert len(result) == 1
        assert result[0]["version_id"] == "pinned-v99"
        store.get_active_repo_version.assert_not_called()


# ---------------------------------------------------------------------------
# resolve_agent_prompt_bindings
# ---------------------------------------------------------------------------


class TestResolveAgentPromptBindings:
    def test_no_bindings_returns_empty(self):
        from agentbox.core.workspaces.prep import resolve_agent_prompt_bindings

        store = _make_store(prompt_bindings=[])
        assert resolve_agent_prompt_bindings(store, "agent1") == []

    def test_hydrates_binding(self):
        from agentbox.core.workspaces.prep import resolve_agent_prompt_bindings

        binding = _simple_prompt_binding()
        resource = {
            "id": "r1",
            "slug": "docs",
            "type": "document",
            "display_name": "My Docs",
        }
        active_v = {"id": "v2"}
        version = {"content_hash": "cafebabe"}
        blobs = [{"path": "content.md", "content": b"# Hello"}]
        store = _make_store(
            prompt_bindings=[binding],
            resource=resource,
            active_version=active_v,
            version=version,
            blobs=blobs,
        )

        result = resolve_agent_prompt_bindings(store, "agent1")

        assert len(result) == 1
        r = result[0]
        assert r["binding_id"] == "pb1"
        assert r["marker"] == "docs"
        assert r["mode"] == "inline"
        assert r["content_hash"] == "cafebabe"
        assert r["blobs"] == blobs
        assert r["required"] is True

    def test_skips_missing_resource(self):
        from agentbox.core.workspaces.prep import resolve_agent_prompt_bindings

        store = _make_store(prompt_bindings=[_simple_prompt_binding()], resource=None)
        assert resolve_agent_prompt_bindings(store, "agent1") == []

    def test_skips_no_active_version(self):
        from agentbox.core.workspaces.prep import resolve_agent_prompt_bindings

        resource = {"id": "r1", "slug": "x", "type": "document", "display_name": "x"}
        store = _make_store(
            prompt_bindings=[_simple_prompt_binding()],
            resource=resource,
            active_version=None,
        )
        assert resolve_agent_prompt_bindings(store, "agent1") == []


# ---------------------------------------------------------------------------
# render_env_doc
# ---------------------------------------------------------------------------


class TestRenderEnvDoc:
    def test_ephemeral_workspace_skips(self, tmp_path: Path):
        from agentbox.core.workspaces.prep import render_env_doc

        store = _make_store()
        result = render_env_doc(store, "<ephemeral>", tmp_path)
        assert result == []
        assert not (tmp_path / "CLAUDE.md").exists()

    def test_no_active_doc_skips(self, tmp_path: Path):
        from agentbox.core.workspaces.prep import render_env_doc

        store = _make_store(active_env_doc=None)
        result = render_env_doc(store, "ws1", tmp_path)
        assert result == []

    def test_renders_both_files(self, tmp_path: Path):
        from agentbox.core.workspaces.prep import render_env_doc

        doc_content = {"body": "# Test Project\n\nAn overview."}
        env_doc = {"id": "ver1", "content_json": json.dumps(doc_content)}
        store = _make_store(active_env_doc=env_doc)

        entries = render_env_doc(store, "ws1", tmp_path)

        claude_md = tmp_path / "CLAUDE.md"
        agents_md = tmp_path / "AGENTS.md"
        assert claude_md.exists()
        assert agents_md.exists()
        # Both files get the identical raw body.
        assert claude_md.read_text() == doc_content["body"]
        assert agents_md.read_text() == doc_content["body"]

        assert len(entries) == 2
        roles = {e["role"] for e in entries}
        assert roles == {"env_doc"}
        files = {e["file"] for e in entries}
        assert files == {"CLAUDE.md", "AGENTS.md"}
        for e in entries:
            assert e["workspace_id"] == "ws1"
            assert e["env_doc_version_id"] == "ver1"
            assert e["bytes"] > 0

    def test_invalid_content_json_returns_empty(self, tmp_path: Path):
        from agentbox.core.workspaces.prep import render_env_doc

        env_doc = {"id": "ver2", "content_json": "not-json{{{"}
        store = _make_store(active_env_doc=env_doc)
        result = render_env_doc(store, "ws1", tmp_path)
        assert result == []

    def test_dict_content_json(self, tmp_path: Path):
        from agentbox.core.workspaces.prep import render_env_doc

        doc_content = {"body": "# Dict Project"}
        env_doc = {"id": "ver3", "content_json": doc_content}
        store = _make_store(active_env_doc=env_doc)

        entries = render_env_doc(store, "ws1", tmp_path)
        assert len(entries) == 2
        assert "Dict Project" in (tmp_path / "CLAUDE.md").read_text()


# ---------------------------------------------------------------------------
# snapshot helpers
# ---------------------------------------------------------------------------


class TestSnapshotHelpers:
    def test_workspace_outcomes_to_snapshot(self):
        from agentbox.core.resources.binding_materialize import MaterializeOutcome
        from agentbox.core.workspaces.prep import workspace_outcomes_to_snapshot

        outcomes = [
            MaterializeOutcome(
                binding_id="b1",
                resource_id="r1",
                version_id="v1",
                content_hash="abc",
                target_path="skills/foo",
                files_written=3,
                mode="copy",
            )
        ]
        entries = workspace_outcomes_to_snapshot(outcomes)
        assert len(entries) == 1
        e = entries[0]
        assert e["role"] == "workspace_file"
        assert e["binding_id"] == "b1"
        assert e["files_written"] == 3
        assert e["skipped"] is False

    def test_prompt_resolution_to_snapshot(self):
        from agentbox.core.agents.composition.resolver import PromptResolution, ResolvedBinding
        from agentbox.core.workspaces.prep import prompt_resolution_to_snapshot

        rb = ResolvedBinding(
            binding_id="pb1",
            marker="docs",
            resource_id="r1",
            version_id="v1",
            content_hash="hash",
            type="document",
            mode="inline",
            rendered="# Hello",
            required=True,
        )
        resolution = PromptResolution(
            rendered_prompt="rendered",
            snapshot=[rb],
            unresolved_markers=[],
            warnings=[],
        )
        entries = prompt_resolution_to_snapshot(resolution)
        assert len(entries) == 1
        e = entries[0]
        assert e["role"] == "prompt_embed"
        assert e["marker"] == "docs"
