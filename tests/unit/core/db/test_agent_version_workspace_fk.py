"""agent_versions.workspace_name is derived + coerced on write.

The column mirrors the config's ``workspace`` ref but only ever holds an
existing workspace name — a dangling or absent ref coerces to NULL (→ default),
so the FK column can never point at a phantom workspace.
"""

from __future__ import annotations

import json

from agentbox.core.data._util import now_iso
from agentbox.core.db import AgentVersionManager, WorkspaceManager
from agentbox.core.db.database import Database


def _insert(mgr: AgentVersionManager, agent_id: str, workspace: str | None) -> int:
    config = {"id": agent_id, "workspace": workspace} if workspace else {"id": agent_id}
    return mgr.insert_version(
        agent_id=agent_id,
        version=1,
        source_path="",
        source_format="db",
        content_snapshot="{}",
        prompt_snapshot="",
        content_hash="h",
        author="test",
        changelog="",
        created_at=now_iso(),
        config_json=json.dumps(config),
    )


def test_workspace_name_kept_when_ref_exists(db: Database) -> None:
    workspaces: WorkspaceManager = db.workspaces
    versions: AgentVersionManager = db.agent_versions
    workspaces.insert(name="realws")

    vid = _insert(versions, "a-real", "realws")

    assert versions.get_by_id(vid)["workspace_name"] == "realws"


def test_workspace_name_nulled_when_ref_dangles(db: Database) -> None:
    versions: AgentVersionManager = db.agent_versions

    vid = _insert(versions, "a-ghost", "ghost-ws")  # no such workspace

    assert versions.get_by_id(vid)["workspace_name"] is None


def test_workspace_name_null_when_ref_absent(db: Database) -> None:
    versions: AgentVersionManager = db.agent_versions

    vid = _insert(versions, "a-none", None)

    assert versions.get_by_id(vid)["workspace_name"] is None
