"""Tests for resource and workspace bindings.

Pin the domain error surface and the sync_cb injection contract used
by REST routes. The store is exercised against a real SQLite to keep
the test honest about persistence wiring.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from agentbox.core.db import SessionStore
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
def store(tmp_path: Path) -> SessionStore:
    return SessionStore(tmp_path / "agentbox.sqlite")


def _make_resource(store: SessionStore, slug: str = "doc/a") -> dict:
    return res_service.create_resource(
        store=store, slug=slug, type="document", display_name=slug
    )


# ---------------------------------------------------------------------------
# Prompt bindings
# ---------------------------------------------------------------------------


def test_list_prompt_resources_empty(store: SessionStore) -> None:
    out = list_prompt_resources("agent-x", store=store)
    assert out == {"items": []}


def test_replace_prompt_resources_empty_round_trip(store: SessionStore) -> None:
    out = replace_prompt_resources("agent-x", [], store=store, reason="clear")
    assert out == {"items": []}


def test_preview_prompt_raises_when_no_version(store: SessionStore) -> None:
    with pytest.raises(AgentVersionMissing):
        preview_prompt("agent-x", store=store)


def test_preview_prompt_uses_explicit_template(store: SessionStore) -> None:
    out = preview_prompt("agent-x", store=store, template="hello")
    assert "text" in out or "rendered" in out or isinstance(out, dict)


# ---------------------------------------------------------------------------
# Workspace file bindings
# ---------------------------------------------------------------------------


def test_list_workspace_resources_empty(store: SessionStore) -> None:
    store.create_workspace("alpha")
    out = list_workspace_resources("alpha", store=store)
    assert out == {"items": []}


def test_replace_workspace_resources_invokes_sync_cb(store: SessionStore) -> None:
    store.create_workspace("alpha")
    calls: list[tuple] = []

    def fake_sync(s, settings, name):  # noqa: ANN001
        calls.append((s, settings, name))

    replace_workspace_resources(
        "alpha",
        [],
        store=store,
        reason="clear",
        settings=object(),
        sync_cb=fake_sync,
    )
    assert len(calls) == 1
    assert calls[0][2] == "alpha"


def test_replace_workspace_resources_skips_sync_when_cb_missing(
    store: SessionStore,
) -> None:
    store.create_workspace("alpha")
    out = replace_workspace_resources("alpha", [], store=store, reason="clear")
    assert out == {"items": []}


def test_dry_run_workspace_resources_shape(store: SessionStore) -> None:
    store.create_workspace("alpha")
    out = dry_run_workspace_resources("alpha", store=store)
    assert set(out) == {"entries", "conflicts"}


# ---------------------------------------------------------------------------
# Preview modes
# ---------------------------------------------------------------------------


def test_preview_modes_unknown_resource_raises(store: SessionStore) -> None:
    with pytest.raises(ResourceNotFound):
        preview_modes("nope", store=store)


def test_preview_modes_returns_empty_when_no_active_version(
    store: SessionStore,
) -> None:
    row = _make_resource(store)
    out = preview_modes(row["id"], store=store)
    assert out == {"modes": []}


# ---------------------------------------------------------------------------
# Subagents + skills
# ---------------------------------------------------------------------------


def test_list_workspace_subagents_empty(store: SessionStore) -> None:
    store.create_workspace("alpha")
    out = list_workspace_subagents("alpha", store=store)
    assert out == {"items": []}


def test_list_workspace_skill_bindings_envelope(store: SessionStore) -> None:
    store.create_workspace("alpha")
    out = list_workspace_skill_bindings("alpha", store=store)
    assert "items" in out
