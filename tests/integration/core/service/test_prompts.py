"""Tests for ``core.service.agents.prompts`` — the use-case wrappers.

Model: versions are immutable; the latest version is current; a "save"
writes a new version only when content changed (content-hash dedup).
There is no draft/publish two-step.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest
from agentbox.core.data import AgentDef
from agentbox.core.db.database import Database
import agentbox.core.service.agents as prompts_service
from agentbox.core.service.agents import AgentNotFound
from agentbox.core.service.agents import AgentService


def _seed_agent(
    store: Database,
    agent_id: str,
    prompt_content: str = "",
) -> None:
    agent = AgentDef.model_validate({"id": agent_id, "description": "x"})
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=UserWarning)
        config_json = agent.model_dump_json()
    row = AgentService().create_version(
        agent_id=agent_id,
        source_path="",
        content_snapshot=config_json,
        prompt_snapshot="",
        content_hash="x",
        config_json=config_json,
        prompt_content=prompt_content or None,
        source="manifest",
    )
    AgentService().activate_version(agent_id, row["id"])


@pytest.fixture
def store(tmp_path: Path) -> Database:
    return Database(tmp_path / "agentbox.sqlite")


def test_get_prompt_raises_when_unknown(store: Database) -> None:
    with pytest.raises(AgentNotFound):
        prompts_service.get_prompt(
            "missing", agent_defs=store.agent_defs, agent_versions=store.agent_versions, prompt_versions=store.prompt_versions
        )


def test_get_prompt_reads_db_content(store: Database) -> None:
    _seed_agent(store, "alpha", prompt_content="from-db")
    doc = prompts_service.get_prompt("alpha", agent_defs=store.agent_defs, agent_versions=store.agent_versions, prompt_versions=store.prompt_versions)
    assert doc.content == "from-db"


def test_put_prompt_creates_version(store: Database) -> None:
    _seed_agent(store, "alpha", prompt_content="")
    doc = prompts_service.put_prompt(
        "alpha",
        "new body",
        agent_defs=store.agent_defs, prompt_versions=store.prompt_versions,
    )
    assert doc.content == "new body"
    versions = AgentService().list_prompt_versions("alpha")
    assert any(v["content"] == "new body" for v in versions)


def test_put_prompt_identical_content_is_noop(store: Database) -> None:
    """Saving identical content twice does not create a second version."""
    _seed_agent(store, "alpha", prompt_content="")
    prompts_service.put_prompt(
        "alpha", "body", agent_defs=store.agent_defs, prompt_versions=store.prompt_versions,
    )
    prompts_service.put_prompt(
        "alpha", "body", agent_defs=store.agent_defs, prompt_versions=store.prompt_versions,
    )
    versions = AgentService().list_prompt_versions("alpha")
    assert len(versions) == 1


def test_list_versions_raises_when_unknown(store: Database) -> None:
    with pytest.raises(AgentNotFound):
        prompts_service.list_versions("missing", agent_defs=store.agent_defs, prompt_versions=store.prompt_versions)


def test_list_versions_returns_shape_when_empty(store: Database) -> None:
    _seed_agent(store, "alpha")
    payload = prompts_service.list_versions("alpha", agent_defs=store.agent_defs, prompt_versions=store.prompt_versions)
    assert payload["agent_id"] == "alpha"
    assert payload["versions"] == []
    assert payload["active_version"] is None
    assert "draft_version" not in payload


def test_get_version_returns_none_when_missing(store: Database) -> None:
    _seed_agent(store, "alpha")
    assert prompts_service.get_version("alpha", 42, agent_defs=store.agent_defs, prompt_versions=store.prompt_versions) is None


def test_save_creates_version_latest_is_current(store: Database) -> None:
    """save_prompt_version inserts a version; the latest version is current."""
    _seed_agent(store, "alpha")
    svc = AgentService()
    v1 = svc.save_prompt_version("alpha", "first body", author="tester")
    assert v1["version"] == 1
    assert v1["content"] == "first body"

    # Latest is current.
    latest = svc.get_latest_prompt("alpha")
    assert latest is not None
    assert latest["version"] == 1

    # Save a second version.
    v2 = svc.save_prompt_version("alpha", "second body", author="tester")
    assert v2["version"] == 2

    latest2 = svc.get_latest_prompt("alpha")
    assert latest2 is not None
    assert latest2["version"] == 2

    # All versions are listed newest first.
    all_versions = svc.list_prompt_versions("alpha")
    assert [v["version"] for v in all_versions] == [2, 1]


def test_save_identical_content_is_noop(store: Database) -> None:
    """Identical content produces no extra version."""
    _seed_agent(store, "alpha")
    svc = AgentService()
    row1 = svc.save_prompt_version("alpha", "same body")
    row2 = svc.save_prompt_version("alpha", "same body")
    # No new row; same version returned.
    assert row1["version"] == row2["version"]
    assert len(svc.list_prompt_versions("alpha")) == 1


def test_version_detail_has_no_is_draft_field(store: Database) -> None:
    """PromptVersionDetail must not carry an is_draft field."""
    _seed_agent(store, "alpha")
    svc = AgentService()
    svc.save_prompt_version("alpha", "content")
    detail = prompts_service.get_version(
        "alpha", 1, agent_defs=store.agent_defs, prompt_versions=store.prompt_versions
    )
    assert detail is not None
    assert "is_draft" not in detail


def test_list_versions_payload_has_no_draft_version_key(store: Database) -> None:
    """PromptVersionListResult must not carry a draft_version field."""
    _seed_agent(store, "alpha")
    payload = prompts_service.list_versions(
        "alpha", agent_defs=store.agent_defs, prompt_versions=store.prompt_versions
    )
    assert "draft_version" not in payload
