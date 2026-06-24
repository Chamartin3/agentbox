import pytest
from agentbox.core.db import SessionStore, agents, now_iso


@pytest.fixture
def store(tmp_path):
    s = SessionStore(tmp_path / "agentbox.sqlite")
    with s.engine.begin() as conn:
        conn.execute(
            agents.insert().values(
                id="agent-1", name="Test Agent", created_at=now_iso()
            )
        )
    return s


def test_grant_and_list(store):
    store.grant_agent_tool("agent-1", "cv.score", "initial grant", actor="tester")
    grants = store.list_agent_tool_grants("agent-1")
    assert len(grants) == 1
    assert grants[0]["tool_name"] == "cv.score"
    assert grants[0]["revoked_at"] is None


def test_list_active_grants(store):
    store.grant_agent_tool("agent-1", "cv.score", "grant it")
    store.grant_agent_tool("agent-1", "cv.validate", "grant it too")
    active = store.list_active_grants("agent-1")
    assert active == {"cv.score", "cv.validate"}


def test_revoke(store):
    store.grant_agent_tool("agent-1", "cv.score", "grant")
    store.revoke_agent_tool("agent-1", "cv.score", "no longer needed", actor="admin")
    active = store.list_active_grants("agent-1")
    assert "cv.score" not in active


def test_include_revoked(store):
    store.grant_agent_tool("agent-1", "cv.score", "grant")
    store.revoke_agent_tool("agent-1", "cv.score", "revoke it")
    all_grants = store.list_agent_tool_grants("agent-1", include_revoked=True)
    assert len(all_grants) == 1
    assert all_grants[0]["revoked_at"] is not None


def test_re_grant_after_revoke(store):
    store.grant_agent_tool("agent-1", "cv.score", "first grant")
    store.revoke_agent_tool("agent-1", "cv.score", "revoke")
    store.grant_agent_tool("agent-1", "cv.score", "re-grant after review")
    active = store.list_active_grants("agent-1")
    assert "cv.score" in active
    all_rows = store.list_agent_tool_grants("agent-1", include_revoked=True)
    assert len(all_rows) == 1


def test_revoke_nonexistent_raises(store):
    with pytest.raises(ValueError, match="No active grant"):
        store.revoke_agent_tool("agent-1", "cv.score", "nothing to revoke")


def test_short_changelog_raises(store):
    with pytest.raises(ValueError, match="at least 3 characters"):
        store.grant_agent_tool("agent-1", "cv.score", "ab")
