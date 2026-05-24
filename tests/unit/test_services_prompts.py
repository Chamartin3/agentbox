"""Tests for ``core.service.prompts`` — the use-case wrappers.

Both the REST routes and MCP tools now go through this module, so we
pin: agent-not-found raises ``AgentNotFound``; reading falls back from
DB to disk; writing both updates disk and captures a version.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest
from agentbox.core.data import AgentDef
from agentbox.core.data import SessionStore
from agentbox.core.service import prompts as prompts_service
from agentbox.core.service.prompts import AgentNotFound


def _seed_agent_with_prompt(
    store: SessionStore,
    agent_id: str,
    prompt_path: str,
    prompt_content: str = "",
) -> None:
    agent = AgentDef.model_validate(
        {"id": agent_id, "description": "x", "prompt_path": prompt_path}
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=UserWarning)
        config_json = agent.model_dump_json()
    row = store.create_version(
        agent_id=agent_id,
        source_path="",
        source_format="db_only",
        content_snapshot=config_json,
        prompt_snapshot="",
        content_hash="x",
        config_json=config_json,
        prompt_content=prompt_content,
        source="manifest",
    )
    store.activate_version(agent_id, row["id"])


@pytest.fixture
def store(tmp_path: Path) -> SessionStore:
    return SessionStore(tmp_path / "db.sqlite")


def test_get_prompt_raises_when_unknown(store: SessionStore, tmp_path: Path) -> None:
    with pytest.raises(AgentNotFound):
        prompts_service.get_prompt(
            "missing", store=store, project_root=tmp_path
        )


def test_get_prompt_reads_db_content(store: SessionStore, tmp_path: Path) -> None:
    _seed_agent_with_prompt(
        store, "alpha", prompt_path="prompts/alpha.md", prompt_content="from-db"
    )
    doc = prompts_service.get_prompt("alpha", store=store, project_root=tmp_path)
    assert doc.content == "from-db"


def test_put_prompt_writes_disk_and_creates_version(
    store: SessionStore, tmp_path: Path
) -> None:
    _seed_agent_with_prompt(
        store, "alpha", prompt_path="prompts/alpha.md", prompt_content=""
    )
    doc = prompts_service.put_prompt(
        "alpha",
        "new body",
        store=store,
        project_root=tmp_path,
    )
    assert doc.content == "new body"
    disk = (tmp_path / "prompts" / "alpha.md").read_text(encoding="utf-8")
    assert disk == "new body"
    # sync_prompt_from_disk captured a new prompt_versions row
    versions = store.list_prompt_versions("alpha")
    assert any(v["content"] == "new body" for v in versions)


def test_list_versions_raises_when_unknown(store: SessionStore) -> None:
    with pytest.raises(AgentNotFound):
        prompts_service.list_versions("missing", store=store)


def test_list_versions_returns_shape_when_empty(store: SessionStore) -> None:
    _seed_agent_with_prompt(store, "alpha", prompt_path="prompts/alpha.md")
    payload = prompts_service.list_versions("alpha", store=store)
    assert payload["agent_id"] == "alpha"
    assert payload["versions"] == []
    assert payload["active_version"] is None
    assert payload["draft_version"] is None


def test_get_version_returns_none_when_missing(store: SessionStore) -> None:
    _seed_agent_with_prompt(store, "alpha", prompt_path="prompts/alpha.md")
    assert prompts_service.get_version("alpha", 42, store=store) is None


def test_save_draft_then_get_version_roundtrip(
    store: SessionStore, tmp_path: Path
) -> None:
    _seed_agent_with_prompt(store, "alpha", prompt_path="prompts/alpha.md")
    prompts_service.save_draft("alpha", "draft body", store=store, author="tester")
    payload = prompts_service.list_versions("alpha", store=store)
    assert payload["draft_version"] is not None
    fetched = prompts_service.get_version(
        "alpha", payload["draft_version"], store=store
    )
    assert fetched is not None
    assert fetched["content"] == "draft body"
    assert fetched["is_draft"] is True
