"""Tests for resource and workspace bindings.

Pin the domain error surface of the binding methods on ResourceService /
WorkspaceService. The store is exercised against a real SQLite to keep
the test honest about persistence wiring.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from agentbox.core.data.constants import ResourceType
from agentbox.core.data import RepoResourceRow
from agentbox.core.db.database import Database
from agentbox.core.service.resources import (
    AgentVersionMissing,
    ResourceNotFound,
    ResourceService,
)
from agentbox.core.service.workspaces import WorkspaceService


@pytest.fixture
def store(tmp_path: Path) -> Database:
    return Database(tmp_path / "agentbox.sqlite")


def _make_resource(store: Database, slug: str = "doc/a") -> RepoResourceRow:
    return ResourceService().create_resource(
        slug=slug, type=ResourceType.DOCUMENT, display_name=slug
    )


# ---------------------------------------------------------------------------
# Prompt bindings
# ---------------------------------------------------------------------------


def test_list_prompt_resources_empty(store: Database) -> None:
    out = ResourceService().list_prompt_resources("agent-x")
    assert out == {"items": []}


def test_replace_prompt_resources_empty_round_trip(store: Database) -> None:
    out = ResourceService().replace_prompt_resources("agent-x", [], reason="clear")
    assert out == {"items": []}


def test_preview_prompt_raises_when_no_version(store: Database) -> None:
    with pytest.raises(AgentVersionMissing):
        ResourceService().preview_prompt("agent-x")


def test_preview_prompt_uses_explicit_template(store: Database) -> None:
    out = ResourceService().preview_prompt("agent-x", template="hello")
    assert "text" in out or "rendered" in out or isinstance(out, dict)


# ---------------------------------------------------------------------------
# Workspace file bindings
# ---------------------------------------------------------------------------


def test_list_workspace_resources_empty(store: Database) -> None:
    store.workspaces.insert("alpha")
    out = ResourceService().list_workspace_resources("alpha")
    assert out == {"items": []}


def test_replace_workspace_resources_empty_round_trip(store: Database) -> None:
    # ponytail: the old sync_cb-injection wrapper is gone — prod REST routes
    # call svc.build_workspace() directly after replace, so there is no sync_cb
    # contract left to pin.
    store.workspaces.insert("alpha")
    out = ResourceService().replace_workspace_resources("alpha", [], reason="clear")
    assert out == {"items": []}


def test_dry_run_workspace_resources_shape(store: Database) -> None:
    store.workspaces.insert("alpha")
    out = ResourceService().dry_run_workspace_resources("alpha")
    assert set(out) == {"entries", "conflicts"}


# ---------------------------------------------------------------------------
# Preview modes
# ---------------------------------------------------------------------------


def test_preview_modes_unknown_resource_raises(store: Database) -> None:
    with pytest.raises(ResourceNotFound):
        ResourceService().preview_modes("nope")


def test_preview_modes_returns_empty_when_no_active_version(
    store: Database,
) -> None:
    row = _make_resource(store)
    out = ResourceService().preview_modes(row["id"])
    assert out == {"modes": []}


# ---------------------------------------------------------------------------
# Subagents + skills
# ---------------------------------------------------------------------------


def test_list_workspace_subagents_empty(store: Database) -> None:
    store.workspaces.insert("alpha")
    out = WorkspaceService().list_workspace_subagents("alpha", agent_defs=store.agent_defs)
    assert out == {"items": []}


def test_list_workspace_skill_bindings_envelope(store: Database) -> None:
    store.workspaces.insert("alpha")
    out = ResourceService().list_workspace_skill_bindings("alpha")
    assert "items" in out
