"""WorkspaceReadManager.list_workspace_engines — the build's default engine set."""

from __future__ import annotations

import uuid

from agentbox.core.data._util import now_iso
from agentbox.core.db import WorkspaceReadManager
from agentbox.core.db.database import Database


def _make_agent(db: Database, agent_id: str) -> None:
    now = now_iso()
    db.agent_meta.insert(
        agent_id=agent_id, sync_mode="manual", export_to_disk=0,
        created_at=now, updated_at=now,
    )
    db.agent_versions.insert_version(
        agent_id=agent_id, version=1, source_path="a.toml", source_format="yaml",
        content_snapshot="s", prompt_snapshot="p", content_hash="h",
        author="t", changelog="c", is_legacy=0, created_at=now,
        activate_for=agent_id, activated_at=now,
    )


def _make_profile(db: Database, backend: str, *, system_default: bool = False) -> str:
    now = now_iso()
    pid = f"prof-{uuid.uuid4().hex[:8]}"
    db.runner_profiles.create_one(
        id=pid, name=pid, backend=backend,
        is_system_default=1 if system_default else 0,
        created_at=now, updated_at=now,
    )
    return pid


def test_no_agents_is_empty(db: Database) -> None:
    read = WorkspaceReadManager(db._engine)
    assert read.list_workspace_engines(f"ws-{uuid.uuid4().hex[:8]}") == set()


def test_bound_agent_uses_its_backend(db: Database) -> None:
    read = WorkspaceReadManager(db._engine)
    ws = f"ws-{uuid.uuid4().hex[:8]}"
    _make_agent(db, ws)  # main agent == workspace id
    now = now_iso()
    db.runner_profiles.set_agent_profile(ws, _make_profile(db, "opencode"), now, now)
    assert read.list_workspace_engines(ws) == {"opencode"}


def test_unbound_agent_falls_back_to_system_default(db: Database) -> None:
    read = WorkspaceReadManager(db._engine)
    ws = f"ws-{uuid.uuid4().hex[:8]}"
    _make_agent(db, ws)  # agent exists but no profile bound
    _make_profile(db, "claude_code", system_default=True)
    assert read.list_workspace_engines(ws) == {"claude_code"}
