"""Plan 122 Phase C: forbid/unforbid write config_json.runtime.forbidden_tools.

The crux is the write path: a runtime-section edit must survive a reload
(``from_db_row`` → ``RuntimeConfig.from_agent``), because ``patch_agent_config``
would have dropped it (it rebuilds config from a fresh AgentDef with no
``_config_json``). These tests prove the direct-config versioned write holds.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest
from agentbox.core.agents import RuntimeConfig
from agentbox.core.data import AgentDef
from agentbox.core.db.database import Database
from agentbox.core.service.agents import AgentService


def _seed_agent(store: Database, agent_id: str, kind: str = "token") -> None:
    agent = AgentDef.model_validate(
        {"id": agent_id, "description": "t", "runner": {"kind": kind}}
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
        prompt_content="",
        source="manifest",
    )
    AgentService().activate_version(agent_id, row["id"])


def _forbidden(agent_id: str, store: Database) -> tuple[str, ...]:
    reloaded = store.agent_defs.get(agent_id)
    assert reloaded is not None
    return RuntimeConfig.from_agent(reloaded).forbidden_tools


@pytest.fixture
def store(tmp_path: Path) -> Database:
    s = Database(tmp_path / "agentbox.sqlite")
    _seed_agent(s, "a.gent")
    return s


def test_forbid_round_trips_through_config_json(store: Database) -> None:
    AgentService().forbid_tool("a.gent", "shell.exec", "deny shell", actor="tester")
    assert _forbidden("a.gent", store) == ("shell.exec",)


def test_unforbid_removes(store: Database) -> None:
    AgentService().forbid_tool("a.gent", "shell.exec", "deny shell")
    AgentService().unforbid_tool("a.gent", "shell.exec", "allow again")
    assert _forbidden("a.gent", store) == ()


def test_forbid_is_cumulative_and_sorted(store: Database) -> None:
    AgentService().forbid_tool("a.gent", "shell.exec", "deny shell")
    AgentService().forbid_tool("a.gent", "fs.read", "deny read")
    assert _forbidden("a.gent", store) == ("fs.read", "shell.exec")


def test_forbid_non_canonical_raises(store: Database) -> None:
    with pytest.raises(ValueError, match="canonical"):
        AgentService().forbid_tool("a.gent", "not.a.real.tool", "bogus")


def test_forbid_duplicate_raises(store: Database) -> None:
    AgentService().forbid_tool("a.gent", "shell.exec", "deny shell")
    with pytest.raises(ValueError, match="already forbidden"):
        AgentService().forbid_tool("a.gent", "shell.exec", "again")


def test_unforbid_not_forbidden_raises(store: Database) -> None:
    with pytest.raises(ValueError, match="not currently forbidden"):
        AgentService().unforbid_tool("a.gent", "shell.exec", "nothing to remove")


def test_short_changelog_raises(store: Database) -> None:
    with pytest.raises(ValueError, match="at least 3 characters"):
        AgentService().forbid_tool("a.gent", "shell.exec", "ab")


def test_list_effective_tools_excludes_forbidden(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The backend is resolved from the runner profile / settings default now,
    # not runner.kind — so drive it via AGENTBOX_DEFAULT_BACKEND. claude_code's
    # native tools include shell.exec; forbidding it must drop it from the
    # effective list while other native tools remain.
    monkeypatch.setenv("AGENTBOX_DEFAULT_BACKEND", "claude_code")
    store = Database(tmp_path / "agentbox.sqlite")
    _seed_agent(store, "cc.agent", kind="claude_code")
    AgentService().forbid_tool("cc.agent", "shell.exec", "deny shell")

    names = {t["name"] for t in AgentService().list_effective_tools("cc.agent")}
    assert "shell.exec" not in names
    assert "fs.read" in names
