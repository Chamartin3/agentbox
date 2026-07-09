"""Tests for prompt-binding resolution + run-snapshot helpers.

The old workspace-prep helpers (``resolve_workspace_resources`` /
``render_env_doc``) moved into ``WorkspaceComposer`` / ``WorkspaceRenderer``
(plan 118 Phase E) — those are covered by ``test_compose.py`` and
``test_facade_build.py``. What remains here tests the still-standalone
functions: ``resolve_agent_prompt_bindings`` (agents domain) and the
``core.data.snapshots`` converters.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from agentbox.core.agents import resolve_agent_prompt_bindings
from agentbox.core.data.composition import PromptResolution, ResolvedBinding
from agentbox.core.data.snapshots import (
    prompt_resolution_to_snapshot,
    workspace_outcomes_to_snapshot,
)
from agentbox.core.data.workenv import MaterializeOutcome


def _make_store(*, prompt_bindings: list[dict] | None = None) -> MagicMock:
    store = MagicMock()
    store.agent_prompt_resource_bindings.list_for_agent.return_value = prompt_bindings or []
    store.resources.get_resource.return_value = None
    store.resource_versions.get_active_version.return_value = None
    store.resource_versions.get_version.return_value = {"content_hash": "abc123"}
    store.resource_blobs.iter_blobs.return_value = iter([])
    return store


def _simple_prompt_binding(bid: str = "pb1", resource_id: str = "r1") -> dict:
    return {
        "id": bid,
        "resource_id": resource_id,
        "marker": "docs",
        "mode": "inline",
        "pinned_version_id": None,
        "required": 1,
    }


class TestResolveAgentPromptBindings:
    def test_no_bindings_returns_empty(self):
        store = _make_store(prompt_bindings=[])
        assert resolve_agent_prompt_bindings(
            store.agent_prompt_resource_bindings,
            store.resources,
            store.resource_versions,
            store.resource_blobs,
            "agent1",
        ) == []

    def test_hydrates_binding(self):
        binding = _simple_prompt_binding()
        resource = {
            "id": "r1",
            "slug": "docs",
            "type": "document",
            "display_name": "My Docs",
        }
        blobs = [{"path": "content.md", "content": b"# Hello"}]
        store = _make_store(prompt_bindings=[binding])
        store.resources.get_resource.return_value = resource
        store.resource_versions.get_active_version.return_value = {"id": "v2"}
        store.resource_versions.get_version.return_value = {"content_hash": "cafebabe"}
        store.resource_blobs.iter_blobs.return_value = iter(blobs)

        result = resolve_agent_prompt_bindings(
            store.agent_prompt_resource_bindings,
            store.resources,
            store.resource_versions,
            store.resource_blobs,
            "agent1",
        )

        assert len(result) == 1
        r = result[0]
        assert r["binding_id"] == "pb1"
        assert r["marker"] == "docs"
        assert r["mode"] == "inline"
        assert r["content_hash"] == "cafebabe"
        assert r["blobs"] == blobs
        assert r["required"] is True

    def test_skips_missing_resource(self):
        store = _make_store(prompt_bindings=[_simple_prompt_binding()])
        store.resources.get_resource.return_value = None
        assert resolve_agent_prompt_bindings(
            store.agent_prompt_resource_bindings,
            store.resources,
            store.resource_versions,
            store.resource_blobs,
            "agent1",
        ) == []

    def test_skips_no_active_version(self):
        store = _make_store(prompt_bindings=[_simple_prompt_binding()])
        store.resources.get_resource.return_value = {
            "id": "r1",
            "slug": "x",
            "type": "document",
            "display_name": "x",
        }
        store.resource_versions.get_active_version.return_value = None
        assert resolve_agent_prompt_bindings(
            store.agent_prompt_resource_bindings,
            store.resources,
            store.resource_versions,
            store.resource_blobs,
            "agent1",
        ) == []


class TestSnapshotHelpers:
    def test_workspace_outcomes_to_snapshot(self):
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
