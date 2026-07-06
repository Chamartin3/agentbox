"""Tests for WorkspaceComposer.compose() (plan 118 Phase D)."""

from __future__ import annotations

import uuid

from agentbox.core.db import WorkspaceReadManager
from agentbox.core.db.database import Database
from agentbox.core.workspaces.compose import WorkspaceComposer


def _composer(db: Database) -> WorkspaceComposer:
    return WorkspaceComposer(WorkspaceReadManager(db._engine))


class TestComposeEdgeCases:
    def test_ephemeral_returns_empty(self, db: Database) -> None:
        bp = _composer(db).compose("<ephemeral>")
        assert bp.workspace_id == "<ephemeral>"
        assert bp.bindings == ()
        assert bp.subagents == ()
        assert bp.permissions is None
        assert bp.env_doc_body is None
        assert bp.env_doc_version_id is None
        assert bp.secret_keys == ()
        assert bp.config.agents == []

    def test_empty_workspace(self, db: Database) -> None:
        ws = db.workspaces.insert(name=f"ws-{uuid.uuid4().hex[:8]}")
        wsid = ws["name"]
        bp = _composer(db).compose(wsid)
        assert bp.workspace_id == wsid
        assert bp.bindings == ()
        assert bp.subagents == ()
        assert bp.config.name == wsid
        # recipes come from list_recipes() — a tuple regardless of what's installed
        assert isinstance(bp.recipes, tuple)


class TestComposeBindings:
    def test_binding_resolved(self, db: Database) -> None:
        ws = db.workspaces.insert(name=f"ws-{uuid.uuid4().hex[:8]}")
        wsid = ws["name"]
        resource = db.resources.create_resource(
            slug=f"res-{uuid.uuid4().hex[:8]}",
            type="document",
            display_name="Doc",
        )
        rid = resource["id"]
        db.resource_versions.import_version(
            rid,
            [("doc.md", b"hello", None, None)],
            import_source="upload",
            changelog="initial",
        )
        db.workspace_file_resource_bindings.replace_for_workspace(
            wsid, [{"resource_id": rid}], reason="test"
        )

        bp = _composer(db).compose(wsid)

        assert len(bp.bindings) == 1
        binding = bp.bindings[0]
        assert binding.resource_id == rid
        assert binding.type == "document"
        assert binding.slug == resource["slug"]
        assert binding.content_hash
        assert len(binding.blobs) >= 1
        # also surfaces as an id-only ResourceRef in the engine-agnostic config
        assert any(ref.id == rid for ref in bp.config.resources)
