from pathlib import Path

import pytest
from agentbox.core.data import now_iso
from agentbox.core.db.database import Database
from agentbox.core.db.agents.agent import Agent
from agentbox.core.service.agents import AgentService

agents = Agent.__table__


@pytest.fixture
def store(tmp_path: Path) -> Database:
    s = Database(tmp_path / "agentbox.sqlite")
    with s.engine.begin() as conn:
        conn.execute(
            agents.insert().values(
                id="agent-1", name="Test Agent", created_at=now_iso()
            )
        )
    return s


def test_grant_and_list(store: Database) -> None:
    AgentService().grant_tool("agent-1", "cv.score", "initial grant", actor="tester")
    grants = AgentService().list_tool_grants("agent-1")
    assert len(grants) == 1
    assert grants[0]["tool_name"] == "cv.score"
    assert grants[0]["revoked_at"] is None


def test_list_active_grants(store: Database) -> None:
    AgentService().grant_tool("agent-1", "cv.score", "grant it")
    AgentService().grant_tool("agent-1", "cv.validate", "grant it too")
    active = AgentService().active_grants("agent-1")
    assert active == {"cv.score", "cv.validate"}


def test_revoke(store: Database) -> None:
    AgentService().grant_tool("agent-1", "cv.score", "grant")
    AgentService().revoke_tool("agent-1", "cv.score", "no longer needed", actor="admin")
    active = AgentService().active_grants("agent-1")
    assert "cv.score" not in active


def test_include_revoked(store: Database) -> None:
    AgentService().grant_tool("agent-1", "cv.score", "grant")
    AgentService().revoke_tool("agent-1", "cv.score", "revoke it")
    all_grants = AgentService().list_tool_grants("agent-1", include_revoked=True)
    assert len(all_grants) == 1
    assert all_grants[0]["revoked_at"] is not None


def test_re_grant_after_revoke(store: Database) -> None:
    AgentService().grant_tool("agent-1", "cv.score", "first grant")
    AgentService().revoke_tool("agent-1", "cv.score", "revoke")
    AgentService().grant_tool("agent-1", "cv.score", "re-grant after review")
    active = AgentService().active_grants("agent-1")
    assert "cv.score" in active
    all_rows = AgentService().list_tool_grants("agent-1", include_revoked=True)
    assert len(all_rows) == 1


def test_revoke_nonexistent_raises(store: Database) -> None:
    with pytest.raises(ValueError, match="No active grant"):
        AgentService().revoke_tool("agent-1", "cv.score", "nothing to revoke")


def test_short_changelog_raises(store: Database) -> None:
    with pytest.raises(ValueError, match="at least 3 characters"):
        AgentService().grant_tool("agent-1", "cv.score", "ab")
