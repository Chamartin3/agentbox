"""Tests for the enriched read views in ``core.service.agents``.

Covers ``list_agents_enriched`` and ``get_agent_detail`` — the two
helpers extracted from ``api/routes/agents.py``. The point of the
service layer is that the route is now a thin wrapper, so these tests
pin the exact dict shape both surfaces (REST + future MCP reuses)
will see.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest
from agentbox.core.config import Settings
from agentbox.core.data import AgentDef
from agentbox.core.db.database import Database
from agentbox.core.service.agents.service import AgentService


def _make_settings(tmp_path: Path) -> Settings:
    manifest = tmp_path / "agentbox.toml"
    manifest.write_text("", encoding="utf-8")
    return Settings(
        manifest_path=manifest,
        data_dir=tmp_path / "data",
        db_path=tmp_path / "data" / "agentbox.sqlite",
        port=8765,
        host="0.0.0.0",
        agents_dir=None,
        agents_bundle_dir=None,
        prompts_dir=None,
        skills_dir=None,
        outputs_dir=None,
        completion_webhook_url=None,
    )


def _seed_agent(store: Database, agent_id: str) -> None:
    agent = AgentDef.model_validate({"id": agent_id, "description": f"desc-{agent_id}"})
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
        prompt_content="hello prompt",
        source="manifest",
    )
    AgentService().activate_version(agent_id, row["id"])


@pytest.fixture
def store(tmp_path: Path) -> Database:
    return Database(tmp_path / "agentbox.sqlite")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return _make_settings(tmp_path)


def test_list_agents_enriched_returns_dicts_with_run_metadata(
    store: Database, settings: Settings
) -> None:
    _seed_agent(store, "alpha")
    _seed_agent(store, "beta")

    listed = AgentService().list_agents_enriched(settings=settings)
    by_id = {a["id"]: a for a in listed}

    assert set(by_id) == {"alpha", "beta"}
    for entry in listed:
        assert entry["run_count"] == 0
        assert entry["runner_profile_id"] is None
        assert entry["model"] is None
        assert "resolved_workspace" in entry
        assert "version" in entry
        # legacy runner.model field must be scrubbed
        if isinstance(entry.get("runner"), dict):
            assert "model" not in entry["runner"]


def test_list_agents_enriched_empty_when_no_agents(
    store: Database, settings: Settings
) -> None:
    assert AgentService().list_agents_enriched(settings=settings) == []


def test_get_agent_detail_returns_none_for_unknown(
    store: Database, settings: Settings
) -> None:
    assert AgentService().get_agent_detail("missing", settings=settings) is None


def test_get_agent_detail_returns_full_payload(
    store: Database, settings: Settings
) -> None:
    _seed_agent(store, "alpha")
    detail = AgentService().get_agent_detail("alpha", settings=settings)

    assert detail is not None
    assert detail["agent"]["id"] == "alpha"
    # DB prompt content surfaces as the active prompt body
    assert detail["prompt"] == "hello prompt"
    # composed_system / composed_user are present (None or rendered); the
    # exact value depends on whether a system-slot binding exists.
    assert "composed_system" in detail
    assert "composed_user" in detail
    assert detail["workspace"]["path"]
    assert detail["current_version"] == 1
    assert len(detail["versions"]) == 1
    assert detail["versions"][0]["version"] == 1
