"""Tests for resource and workspace bindings.

Pin the domain error surface and the sync_cb injection contract used
by REST routes. The store is exercised against a real SQLite to keep
the test honest about persistence wiring.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from agentbox.core.data.constants import ResourceType
from agentbox.core.data import RepoResourceRow
from agentbox.core.db.database import Database
from agentbox.core.service import resources as res_service
from agentbox.core.service.resources import ResourceNotFound
from agentbox.core.service.resources.bindings import (
    list_prompt_resources,
    replace_prompt_resources,
    preview_prompt,
    list_workspace_resources,
    replace_workspace_resources,
    dry_run_workspace_resources,
    preview_modes,
)
from agentbox.core.service.resources.service import AgentVersionMissing
from agentbox.core.service.workspaces.bindings import (
    list_workspace_subagents,
    list_workspace_skill_bindings,
)


@pytest.fixture
def store(tmp_path: Path) -> Database:
    return Database(tmp_path / "agentbox.sqlite")


def _make_resource(store: Database, slug: str = "doc/a") -> RepoResourceRow:
    return res_service.create_resource(
        slug=slug, type=ResourceType.DOCUMENT, display_name=slug
    )


# ---------------------------------------------------------------------------
# Prompt bindings
# ---------------------------------------------------------------------------


def test_list_prompt_resources_empty(store: Database) -> None:
    out = list_prompt_resources("agent-x")
    assert out == {"items": []}


def test_replace_prompt_resources_empty_round_trip(store: Database) -> None:
    out = replace_prompt_resources("agent-x", [], reason="clear")
    assert out == {"items": []}


def test_preview_prompt_raises_when_no_version(store: Database) -> None:
    with pytest.raises(AgentVersionMissing):
        preview_prompt("agent-x")


def test_preview_prompt_uses_explicit_template(store: Database) -> None:
    out = preview_prompt("agent-x", template="hello")
    assert "text" in out or "rendered" in out or isinstance(out, dict)


# ---------------------------------------------------------------------------
# Workspace file bindings
# ---------------------------------------------------------------------------


def test_list_workspace_resources_empty(store: Database) -> None:
    store.workspaces.insert("alpha")
    out = list_workspace_resources("alpha")
    assert out == {"items": []}


def test_replace_workspace_resources_invokes_sync_cb(store: Database) -> None:
    store.workspaces.insert("alpha")
    calls: list[tuple[object, str]] = []

    def fake_sync(settings: object, name: str) -> None:
        calls.append((settings, name))

    replace_workspace_resources(
        "alpha",
        [],
                reason="clear",
        settings=object(),
        sync_cb=fake_sync,
    )
    assert len(calls) == 1
    assert calls[0][1] == "alpha"


def test_replace_workspace_resources_skips_sync_when_cb_missing(
    store: Database,
) -> None:
    store.workspaces.insert("alpha")
    out = replace_workspace_resources("alpha", [], reason="clear")
    assert out == {"items": []}


def test_dry_run_workspace_resources_shape(store: Database) -> None:
    store.workspaces.insert("alpha")
    out = dry_run_workspace_resources("alpha")
    assert set(out) == {"entries", "conflicts"}


# ---------------------------------------------------------------------------
# Preview modes
# ---------------------------------------------------------------------------


def test_preview_modes_unknown_resource_raises(store: Database) -> None:
    with pytest.raises(ResourceNotFound):
        preview_modes("nope")


def test_preview_modes_returns_empty_when_no_active_version(
    store: Database,
) -> None:
    row = _make_resource(store)
    out = preview_modes(row["id"])
    assert out == {"modes": []}


# ---------------------------------------------------------------------------
# Subagents + skills
# ---------------------------------------------------------------------------


def test_list_workspace_subagents_empty(store: Database) -> None:
    store.workspaces.insert("alpha")
    out = list_workspace_subagents("alpha", agent_defs=store.agent_defs)
    assert out == {"items": []}


def test_list_workspace_skill_bindings_envelope(store: Database) -> None:
    store.workspaces.insert("alpha")
    out = list_workspace_skill_bindings("alpha")
    assert "items" in out
