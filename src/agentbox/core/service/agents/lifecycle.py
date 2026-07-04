from __future__ import annotations

import difflib
import hashlib
import json
import uuid
from agentbox.core.data import (
    AgentDef,
    AgentMetaRow,
    AgentToolGrantRow,
    AgentVersionCommentRow,
    AgentVersionRatingRow,
    AgentVersionRow,
    PromptVersionRow,
)
from agentbox.core.data._util import now_iso
from agentbox.core.data.payload_types import AgentDiffResult, JsonDiffResult
from agentbox.core.db import (
    ActiveAgentVersionManager,
    AgentDefManager,
    AgentMetaManager,
    AgentToolGrantManager,
    AgentVersionCommentManager,
    AgentVersionManager,
    AgentVersionRatingManager,
    PromptVersionManager,
)


# ---------------------------------------------------------------------------
# Internal helpers (replicated from AgentService)
# ---------------------------------------------------------------------------

def _text_diff(a: str, b: str) -> str:
    if a == b:
        return ""
    return "".join(
        difflib.unified_diff(
            a.splitlines(keepends=True), b.splitlines(keepends=True), lineterm=""
        )
    )


def _json_diff(a: str, b: str) -> JsonDiffResult:
    try:
        obj_a = json.loads(a) if a else {}
        obj_b = json.loads(b) if b else {}
    except json.JSONDecodeError:
        return {"from": a, "to": b, "note": "invalid JSON"}
    return {
        "added": {k: obj_b[k] for k in obj_b if k not in obj_a},
        "removed": {k: obj_a[k] for k in obj_a if k not in obj_b},
        "changed": {
            k: {"from": obj_a[k], "to": obj_b[k]}
            for k in obj_a
            if k in obj_b and obj_a[k] != obj_b[k]
        },
    }


def _refresh_meta(
    agent_meta: AgentMetaManager,
    agent_id: str,
    *,
    sync_mode: str,
    export_to_disk: bool,
    source_path: str | None,
    source_format: str | None,
    clear_deleted: bool,
) -> None:
    now = now_iso()
    if agent_meta.get_meta(agent_id) is not None:
        values: dict = {
            "sync_mode": sync_mode,
            "export_to_disk": int(export_to_disk),
            "source_path": source_path,
            "source_format": source_format,
            "updated_at": now,
        }
        if clear_deleted:
            values["deleted_at"] = None
        agent_meta.patch(agent_id, **values)
    else:
        agent_meta.insert(
            agent_id=agent_id,
            sync_mode=sync_mode,
            export_to_disk=int(export_to_disk),
            source_path=source_path,
            source_format=source_format,
            created_at=now,
            updated_at=now,
        )


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def soft_delete_agent(
    agent_versions: AgentVersionManager,
    agent_meta: AgentMetaManager,
    active_agent_versions: ActiveAgentVersionManager,
    agent_id: str,
) -> AgentMetaRow | None:
    """Soft-delete an agent. Returns None if not found."""
    if not agent_versions.exists_for_agent(agent_id):
        return None
    now = now_iso()
    if agent_meta.get_meta(agent_id) is not None:
        agent_meta.patch(agent_id, deleted_at=now, updated_at=now)
    else:
        agent_meta.insert(
            agent_id=agent_id,
            sync_mode="off",
            export_to_disk=0,
            source_path=None,
            source_format=None,
            created_at=now,
            updated_at=now,
            deleted_at=now,
        )
    active_agent_versions.delete_for_agent(agent_id)
    return agent_meta.get_meta(agent_id)


def branch_draft(
    agent_versions: AgentVersionManager,
    agent_id: str,
    *,
    author: str,
) -> AgentVersionRow:
    """Create a new draft version by cloning the active version."""
    active = agent_versions.get_active(agent_id)
    if active is None:
        raise ValueError(f"No active version for agent {agent_id}")
    vid = agent_versions.insert_version(
        copy_files_from=active["id"],
        agent_id=agent_id,
        version=agent_versions.next_version(agent_id),
        source_path=active.get("source_path") or "",
        source_format=active.get("source_format") or "",
        content_snapshot=active.get("content_snapshot") or "",
        prompt_snapshot=active.get("prompt_snapshot") or "",
        content_hash=active.get("content_hash") or "",
        author=author,
        changelog=f"branched from v{active['version']}",
        is_legacy=0,
        created_at=now_iso(),
        config_json=active.get("config_json"),
        prompt_content=active.get("prompt_content"),
        source=active.get("source", "ui"),
    )
    result = agent_versions.get_by_id(vid)
    assert result is not None
    return result


def publish_version(
    agent_versions: AgentVersionManager,
    agent_tool_grants: AgentToolGrantManager,
    active_agent_versions: ActiveAgentVersionManager,
    agent_id: str,
    version: int,
    reason: str,
) -> AgentVersionRow:
    """Publish a draft version (set as active)."""
    if not reason or len(reason) < 3:
        raise ValueError("reason must be at least 3 characters")
    row = agent_versions.get_by_number(agent_id, version)
    if row is None:
        raise ValueError(f"version {version} not found for agent {agent_id}")
    version_id = row["id"]
    old = row.get("changelog") or ""
    values: dict = {"changelog": f"{old}\n\npublish: {reason}" if old else reason}
    try:
        values["resolved_tool_grants"] = sorted(
            {r["tool_name"] for r in agent_tool_grants.list_for_agent(agent_id)}
        )
    except Exception:
        pass
    agent_versions.patch(version_id, **values)
    active_agent_versions.set_pointer(agent_id, version_id, now_iso())
    result = agent_versions.get_by_number(agent_id, version)
    assert result is not None
    return result


def rollback_to(
    agent_versions: AgentVersionManager,
    active_agent_versions: ActiveAgentVersionManager,
    agent_id: str,
    target_version: int,
    reason: str,
    *,
    author: str,
) -> AgentVersionRow:
    """Roll back to a previous agent version (creates a new version)."""
    if not reason or len(reason) < 3:
        raise ValueError("reason must be at least 3 characters")
    target = agent_versions.get_by_number(agent_id, target_version)
    if target is None:
        raise ValueError(f"target_version {target_version} not found for agent {agent_id}")
    latest = agent_versions.get_latest(agent_id)
    next_v = (latest.get("version") or 0) + 1 if latest else 1
    new_vid = agent_versions.insert_version(
        copy_files_from=target["id"],
        agent_id=agent_id,
        version=next_v,
        source_path=target.get("source_path") or "",
        source_format=target.get("source_format") or "",
        content_snapshot=target.get("content_snapshot") or "",
        prompt_snapshot=target.get("prompt_snapshot") or "",
        content_hash=target.get("content_hash") or "",
        author=author,
        changelog=f"rollback to v{target_version}: {reason}",
        is_legacy=0,
        created_at=now_iso(),
        config_json=target.get("config_json"),
        prompt_content=target.get("prompt_content"),
        source=target.get("source", "ui"),
    )
    active_agent_versions.set_pointer(agent_id, new_vid, now_iso())
    result = agent_versions.get_by_id(new_vid)
    assert result is not None
    return result


def get_agent_def(agent_defs: AgentDefManager, agent_id: str) -> AgentDef | None:
    """Get the resolved agent definition."""
    return agent_defs.get(agent_id)


def latest_version(agent_versions: AgentVersionManager, agent_id: str) -> AgentVersionRow | None:
    """Get latest version row for an agent."""
    return agent_versions.get_latest(agent_id)


def get_active_version(agent_versions: AgentVersionManager, agent_id: str) -> AgentVersionRow | None:
    """Get the currently active version for an agent."""
    return agent_versions.get_active(agent_id)


def get_version(
    agent_versions: AgentVersionManager, agent_id: str, version: int
) -> AgentVersionRow | None:
    """Get a specific version by number."""
    return agent_versions.get_by_number(agent_id, version)


def list_versions(
    agent_versions: AgentVersionManager, agent_id: str
) -> list[AgentVersionRow]:
    """List all versions for an agent."""
    return agent_versions.list_for_agent(agent_id)


def create_agent(
    agent_versions: AgentVersionManager,
    agent_meta: AgentMetaManager,
    agent_id: str,
    config_json: dict,
    *,
    prompt_content: str | None = None,
    author: str,
    changelog: str,
    source: str = "cli",
    source_path: str | None = None,
    source_format: str | None = None,
    sync_mode: str = "off",
    export_to_disk: bool = False,
) -> AgentVersionRow:
    """Create a new agent record."""
    if agent_versions.exists_for_agent(agent_id):
        raise ValueError(f"Agent {agent_id!r} already exists")
    config_hash = hashlib.sha256(
        json.dumps(config_json, sort_keys=True).encode()
    ).hexdigest()
    vid = agent_versions.insert_version(
        agent_id=agent_id,
        version=1,
        source_path=source_path or "",
        source_format=source_format or "",
        content_snapshot="",
        prompt_snapshot="",
        content_hash=config_hash,
        author=author,
        changelog=changelog,
        is_legacy=0,
        created_at=now_iso(),
        config_json=json.dumps(config_json, sort_keys=True),
        prompt_content=prompt_content,
        source=source,
    )
    _refresh_meta(
        agent_meta,
        agent_id,
        sync_mode=sync_mode,
        export_to_disk=export_to_disk,
        source_path=source_path,
        source_format=source_format,
        clear_deleted=False,
    )
    result = agent_versions.get_by_id(vid)
    assert result is not None
    return result


def create_version(
    agent_versions: AgentVersionManager,
    agent_id: str,
    source_path: str,
    source_format: str,
    content_snapshot: str,
    prompt_snapshot: str,
    content_hash: str,
    author: str = "system",
    changelog: str = "",
    files: list[dict] | None = None,
    config_json: str | None = None,
    prompt_content: str | None = None,
    source: str = "cli",
) -> AgentVersionRow:
    """Create a new agent version record."""
    vid = agent_versions.insert_version(
        files=files or None,
        agent_id=agent_id,
        version=agent_versions.next_version(agent_id),
        source_path=source_path,
        source_format=source_format,
        content_snapshot=content_snapshot,
        prompt_snapshot=prompt_snapshot,
        content_hash=content_hash,
        author=author,
        changelog=changelog,
        is_legacy=0,
        created_at=now_iso(),
        config_json=config_json,
        prompt_content=prompt_content,
        source=source,
    )
    result = agent_versions.get_by_id(vid)
    assert result is not None
    return result


def get_prompt_version(
    prompt_versions: PromptVersionManager, agent_id: str, version: int
) -> PromptVersionRow | None:
    """Get a specific prompt version."""
    return prompt_versions.get_by_number(agent_id, version)


def list_agent_tool_grants(
    agent_tool_grants: AgentToolGrantManager,
    agent_id: str,
    *,
    include_revoked: bool = False,
) -> list[AgentToolGrantRow]:
    """List tool grants for an agent."""
    return agent_tool_grants.list_for_agent(agent_id, include_revoked=include_revoked)


def grant_agent_tool(
    agent_tool_grants: AgentToolGrantManager,
    agent_id: str,
    tool_name: str,
    changelog: str,
    *,
    actor: str | None = None,
) -> AgentToolGrantRow:
    """Grant tool access to an agent."""
    if len(changelog.strip()) < 3:
        raise ValueError("changelog must be at least 3 characters")
    now = now_iso()
    fields: dict = {
        "changelog": changelog,
        "granted_at": now,
        "granted_by": actor,
        "revoked_at": None,
        "revoked_by": None,
        "revoke_changelog": None,
    }
    existing = agent_tool_grants.get_grant(agent_id, tool_name)
    if existing is None:
        agent_tool_grants.insert(
            id=str(uuid.uuid4()), agent_id=agent_id, tool_name=tool_name, **fields
        )
    else:
        agent_tool_grants.update_by_id(existing["id"], **fields)
    row = agent_tool_grants.get_grant(agent_id, tool_name)
    assert row is not None
    return row


def revoke_agent_tool(
    agent_tool_grants: AgentToolGrantManager,
    agent_id: str,
    tool_name: str,
    changelog: str,
    *,
    actor: str | None = None,
) -> None:
    """Revoke tool access from an agent."""
    agent_tool_grants.revoke_active(
        agent_id, tool_name, revoked_at=now_iso(), revoked_by=actor, revoke_changelog=changelog
    )


def get_rating(
    agent_version_ratings: AgentVersionRatingManager, version_id: int
) -> AgentVersionRatingRow | None:
    """Get the rating row for a version."""
    return agent_version_ratings.latest_for_version(version_id)


def list_comments(
    agent_version_comments: AgentVersionCommentManager, version_id: int
) -> list[AgentVersionCommentRow]:
    """List comments for a version."""
    return agent_version_comments.list_for_version(version_id)


def add_comment(
    agent_version_comments: AgentVersionCommentManager,
    version_id: int,
    author: str,
    body: str,
) -> AgentVersionCommentRow:
    """Add a comment to a version."""
    agent_version_comments.insert(
        version_id=version_id, author=author, body=body, created_at=now_iso()
    )
    comment = agent_version_comments.latest_for_version(version_id)
    assert comment is not None
    return comment


def set_rating(
    agent_version_ratings: AgentVersionRatingManager,
    version_id: int,
    rating: int,
    rater: str,
) -> AgentVersionRatingRow:
    """Set the rating for a version."""
    if not (1 <= rating <= 5):
        raise ValueError(f"rating must be 1-5, got {rating}")
    agent_version_ratings.insert(
        version_id=version_id, rating=rating, rater=rater, rated_at=now_iso()
    )
    result = agent_version_ratings.latest_for_version(version_id)
    assert result is not None
    return result


def diff_versions(
    agent_versions: AgentVersionManager,
    agent_id: str,
    a: int,
    b: int,
) -> AgentDiffResult:
    """Diff two agent versions."""
    va = agent_versions.get_by_number(agent_id, a)
    vb = agent_versions.get_by_number(agent_id, b)
    if va is None or vb is None:
        raise ValueError(f"version not found: {a if va is None else b}")
    return {
        "from_version": a,
        "to_version": b,
        "prompt_diff": _text_diff(va["prompt_snapshot"], vb["prompt_snapshot"]),
        "content_diff": _json_diff(va["content_snapshot"], vb["content_snapshot"]),
    }


def save_prompt_revision(
    agent_versions: AgentVersionManager,
    active_agent_versions: ActiveAgentVersionManager,
    agent_id: str,
    *,
    prompt_content: str,
    author: str = "cli",
    changelog: str = "",
    activate: bool = False,
) -> AgentVersionRow:
    """Save a prompt revision for an agent (creates a new version)."""
    active = agent_versions.get_active(agent_id) or agent_versions.get_latest(agent_id)
    if active is None:
        raise ValueError(f"No version to clone for agent {agent_id}")
    cloned_config = active.get("config_json")
    if cloned_config:
        try:
            cfg_dict = (
                json.loads(cloned_config)
                if isinstance(cloned_config, str)
                else dict(cloned_config)
            )
            cfg_dict["prompt"] = prompt_content
            cloned_config = json.dumps(cfg_dict)
        except (json.JSONDecodeError, TypeError):
            pass
    now = now_iso()
    vid = agent_versions.insert_version(
        copy_files_from=active["id"],
        activate_for=agent_id if activate else None,
        activated_at=now if activate else None,
        agent_id=agent_id,
        version=agent_versions.next_version(agent_id),
        source_path=active.get("source_path") or "",
        source_format=active.get("source_format") or "",
        content_snapshot=active.get("content_snapshot") or "",
        prompt_snapshot=prompt_content,
        content_hash="",
        author=author,
        changelog=changelog or f"prompt edit from v{active['version']}",
        is_legacy=0,
        created_at=now,
        config_json=cloned_config,
        prompt_content=prompt_content,
        source=active.get("source", "ui"),
    )
    result = agent_versions.get_by_id(vid)
    assert result is not None
    return result
