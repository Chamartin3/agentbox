"""Tests for ``core.service.agents.prompts`` — the use-case wrappers.

Both the REST routes and MCP tools now go through this module, so we
pin: agent-not-found raises ``AgentNotFound``; reading falls back from
DB to disk; writing both updates disk and captures a version.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest
from agentbox.core.data import AgentDef
from agentbox.core.db.database import Database
from agentbox.core.service.agents import prompts as prompts_service
from agentbox.core.service.agents.prompts import AgentNotFound
from agentbox.core.service.agents.service import AgentService


def _seed_agent_with_prompt(
    store: Database,
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
    row = AgentService().create_version(
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
    AgentService().activate_version(agent_id, row["id"])


@pytest.fixture
def store(tmp_path: Path) -> Database:
    return Database(tmp_path / "agentbox.sqlite")


def test_get_prompt_raises_when_unknown(store: Database, tmp_path: Path) -> None:
    with pytest.raises(AgentNotFound):
        prompts_service.get_prompt(
            "missing", agent_defs=store.agent_defs, agent_versions=store.agent_versions, prompt_versions=store.prompt_versions, project_root=tmp_path
        )


def test_get_prompt_reads_db_content(store: Database, tmp_path: Path) -> None:
    _seed_agent_with_prompt(
        store, "alpha", prompt_path="prompts/alpha.md", prompt_content="from-db"
    )
    doc = prompts_service.get_prompt("alpha", agent_defs=store.agent_defs, agent_versions=store.agent_versions, prompt_versions=store.prompt_versions, project_root=tmp_path)
    assert doc.content == "from-db"


def test_put_prompt_writes_disk_and_creates_version(
    store: Database, tmp_path: Path
) -> None:
    _seed_agent_with_prompt(
        store, "alpha", prompt_path="prompts/alpha.md", prompt_content=""
    )
    doc = prompts_service.put_prompt(
        "alpha",
        "new body",
        agent_defs=store.agent_defs, prompt_versions=store.prompt_versions,
        project_root=tmp_path,
    )
    assert doc.content == "new body"
    disk = (tmp_path / "prompts" / "alpha.md").read_text(encoding="utf-8")
    assert disk == "new body"
    # sync_prompt_from_disk captured a new prompt_versions row
    versions = AgentService().list_prompt_versions("alpha")
    assert any(v["content"] == "new body" for v in versions)


def test_list_versions_raises_when_unknown(store: Database) -> None:
    with pytest.raises(AgentNotFound):
        prompts_service.list_versions("missing", agent_defs=store.agent_defs, prompt_versions=store.prompt_versions)


def test_list_versions_returns_shape_when_empty(store: Database) -> None:
    _seed_agent_with_prompt(store, "alpha", prompt_path="prompts/alpha.md")
    payload = prompts_service.list_versions("alpha", agent_defs=store.agent_defs, prompt_versions=store.prompt_versions)
    assert payload["agent_id"] == "alpha"
    assert payload["versions"] == []
    assert payload["active_version"] is None
    assert payload["draft_version"] is None


def test_get_version_returns_none_when_missing(store: Database) -> None:
    _seed_agent_with_prompt(store, "alpha", prompt_path="prompts/alpha.md")
    assert prompts_service.get_version("alpha", 42, agent_defs=store.agent_defs, prompt_versions=store.prompt_versions) is None


def test_save_draft_then_get_version_roundtrip(
    store: Database, tmp_path: Path
) -> None:
    _seed_agent_with_prompt(store, "alpha", prompt_path="prompts/alpha.md")
    prompts_service.save_draft("alpha", "draft body", agent_defs=store.agent_defs, prompt_versions=store.prompt_versions, author="tester")
    payload = prompts_service.list_versions("alpha", agent_defs=store.agent_defs, prompt_versions=store.prompt_versions)
    assert payload["draft_version"] is not None
    fetched = prompts_service.get_version(
        "alpha", payload["draft_version"], agent_defs=store.agent_defs, prompt_versions=store.prompt_versions
    )
    assert fetched is not None
    assert fetched["content"] == "draft body"
    assert fetched["is_draft"] is True
