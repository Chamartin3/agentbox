"""Agent creation + version file management — extracted from __init__.py per C10.

Import from ``service.agents`` (the package), never from this module directly.
"""

from __future__ import annotations

import hashlib
import json as _json
from typing import Any, cast

from agentbox.core.agents import build_config_json_payload
from agentbox.core.data.constants import SessionMode
from agentbox.core.data import (
    AgentAlreadyExists,
    AgentDef,
    AgentNotFound,
    AgentVersionRow,
    DuplicateVersionFile,
    VersionFileNotFound,
    VersionFileUploadRow,
    VersionNotDraft,
    VersionNotFound,
)
from agentbox.core.data._util import now_iso
from agentbox.core.db import (
    AgentDefManager,
    AgentMetaManager,
    AgentVersionFileManager,
    AgentVersionManager,
)


def _config_hash(config_json: dict) -> str:
    return hashlib.sha256(
        _json.dumps(config_json, sort_keys=True).encode()
    ).hexdigest()


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


def create_agent_record(
    *,
    agent_versions: AgentVersionManager,
    agent_meta: AgentMetaManager,
    agent_id: str,
    description: str,
    runner: Any,
    prompt: str | None,
    composition: Any,
    tools: list[str] | None,
    tags: list[str] | None,
    workspace: Any,
    session_mode: Any,
    webhook_url: str | None,
    author: str,
    changelog: str,
) -> AgentVersionRow:
    agent_def = AgentDef(
        id=agent_id,
        description=description,
        runner=runner,
        prompt=prompt,
        composition=composition,
        tools=tools or [],
        tags=tags or [],
        workspace=workspace,
        session_mode=cast(SessionMode, session_mode or "headless"),
        webhook_url=webhook_url,
        source_path=None,
        source_format=None,
    )
    config_payload = {
        **agent_def.model_dump(mode="json", exclude_none=True),
        **build_config_json_payload(agent_def),
    }

    # is_agent_deleted: check meta row
    meta = agent_meta.get_meta(agent_id)
    is_deleted = bool(meta and meta.get("deleted_at"))

    if is_deleted:
        # add_agent_version: append a new version, clear deleted_at
        latest = agent_versions.get_latest(agent_id)
        next_v = (latest.get("version") or 0) + 1 if latest else 1
        vid = agent_versions.insert_version(
            agent_id=agent_id,
            version=next_v,
            source_path=None or "",
            source_format=None or "",
            content_snapshot="",
            prompt_snapshot="",
            content_hash=_config_hash(config_payload),
            author=author,
            changelog=changelog,
            is_legacy=0,
            created_at=now_iso(),
            config_json=_json.dumps(config_payload, sort_keys=True),
            prompt_content=prompt,
            source="ui",
        )
        _refresh_meta(
            agent_meta, agent_id,
            sync_mode="off", export_to_disk=False,
            source_path=None, source_format=None,
            clear_deleted=True,
        )
        result = agent_versions.get_by_id(vid)
        assert result is not None
        return result
    try:
        # create_agent: v1, no existence
        if agent_versions.exists_for_agent(agent_id):
            raise ValueError(f"Agent {agent_id!r} already exists")
        vid = agent_versions.insert_version(
            agent_id=agent_id,
            version=1,
            source_path=None or "",
            source_format=None or "",
            content_snapshot="",
            prompt_snapshot="",
            content_hash=_config_hash(config_payload),
            author=author,
            changelog=changelog,
            is_legacy=0,
            created_at=now_iso(),
            config_json=_json.dumps(config_payload, sort_keys=True),
            prompt_content=prompt,
            source="ui",
        )
        _refresh_meta(
            agent_meta, agent_id,
            sync_mode="off", export_to_disk=False,
            source_path=None, source_format=None,
            clear_deleted=False,
        )
        result = agent_versions.get_by_id(vid)
        assert result is not None
        return result
    except ValueError as exc:
        raise AgentAlreadyExists(str(exc)) from exc


def upload_version_file(
    *,
    agent_versions: AgentVersionManager,
    agent_version_files: AgentVersionFileManager,
    agent_id: str,
    version: int,
    kind: str,
    name: str,
    content: str,
) -> VersionFileUploadRow:
    version_record = agent_versions.get_by_number(agent_id, version)
    if version_record is None:
        raise VersionNotFound(f"version {version} not found")
    active = agent_versions.get_active(agent_id)
    if active is not None and active["id"] == version_record["id"]:
        raise VersionNotDraft("cannot modify active version")

    sha256_hash = hashlib.sha256(content.encode()).hexdigest()
    files = agent_version_files.list_for_version(version_record["id"])
    for f in files:
        if f.get("sha256") == sha256_hash:
            raise DuplicateVersionFile("duplicate_sha256")
        if f.get("relative_path") == name:
            raise DuplicateVersionFile("duplicate_path")

    agent_version_files.insert_files(
        version_record["id"],
        [
            {
                "relative_path": name,
                "kind": kind,
                "content": content,
                "sha256": sha256_hash,
            }
        ],
    )
    files = agent_version_files.list_for_version(version_record["id"])
    inserted = next((f for f in files if f.get("sha256") == sha256_hash), None)
    if inserted is None:
        raise RuntimeError("file_insert_failed")
    return {"file": inserted, "sha256": sha256_hash, "size": len(content)}


def delete_version_file(
    *,
    agent_versions: AgentVersionManager,
    agent_version_files: AgentVersionFileManager,
    agent_id: str,
    version: int,
    file_id: int,
) -> None:
    version_record = agent_versions.get_by_number(agent_id, version)
    if version_record is None:
        raise VersionNotFound(f"version {version} not found")
    active = agent_versions.get_active(agent_id)
    if active is not None and active["id"] == version_record["id"]:
        raise VersionNotDraft("not_draft")
    files = agent_version_files.list_for_version(version_record["id"])
    if not any(f.get("id") == file_id for f in files):
        raise VersionFileNotFound(f"file {file_id} not found")
    agent_version_files.delete_file(file_id)


def require_agent_exists(agent_id: str, *, agent_defs: AgentDefManager) -> None:
    if agent_defs.get(agent_id) is not None:
        return
    raise AgentNotFound(agent_id)
