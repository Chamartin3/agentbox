"""Agent creation + version file management — extracted from __init__.py per C10.

Import from ``service.agents`` (the package), never from this module directly.
"""

from __future__ import annotations

import hashlib
from typing import Any, cast

from agentbox.core.agents.config import build_config_json_payload
from agentbox.core.constants import SessionMode
from agentbox.core.db import AgentDef, SessionStore


class AgentAlreadyExists(ValueError):
    """Raised when create_agent_record is called for an existing agent_id."""


class VersionNotFound(LookupError):
    pass


class VersionNotDraft(ValueError):
    pass


class DuplicateVersionFile(ValueError):
    """Same sha256 or relative_path already attached to the draft version."""


class VersionFileNotFound(LookupError):
    pass


def create_agent_record(
    *,
    store: SessionStore,
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
) -> dict:
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
    common_kwargs: dict[str, Any] = dict(
        agent_id=agent_id,
        config_json=config_payload,
        prompt_content=prompt,
        author=author,
        changelog=changelog,
        source="ui",
        source_path=None,
        source_format=None,
        sync_mode="off",
        export_to_disk=False,
    )
    if store.is_agent_deleted(agent_id):
        return store.add_agent_version(**common_kwargs)
    try:
        return store.create_agent(**common_kwargs)
    except ValueError as exc:
        raise AgentAlreadyExists(str(exc)) from exc


def upload_version_file(
    *,
    store: SessionStore,
    agent_id: str,
    version: int,
    kind: str,
    name: str,
    content: str,
) -> dict:
    version_record = store.get_version(agent_id, version)
    if version_record is None:
        raise VersionNotFound(f"version {version} not found")
    active = store.get_active_version(agent_id)
    if active is not None and active["id"] == version_record["id"]:
        raise VersionNotDraft("cannot modify active version")

    sha256_hash = hashlib.sha256(content.encode()).hexdigest()
    files = store.list_version_files(version_record["id"])
    for f in files:
        if f.get("sha256") == sha256_hash:
            raise DuplicateVersionFile("duplicate_sha256")
        if f.get("relative_path") == name:
            raise DuplicateVersionFile("duplicate_path")

    store.insert_version_files(
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
    files = store.list_version_files(version_record["id"])
    inserted = next((f for f in files if f.get("sha256") == sha256_hash), None)
    if inserted is None:
        raise RuntimeError("file_insert_failed")
    return {"file": inserted, "sha256": sha256_hash, "size": len(content)}


def delete_version_file(
    *,
    store: SessionStore,
    agent_id: str,
    version: int,
    file_id: int,
) -> None:
    version_record = store.get_version(agent_id, version)
    if version_record is None:
        raise VersionNotFound(f"version {version} not found")
    active = store.get_active_version(agent_id)
    if active is not None and active["id"] == version_record["id"]:
        raise VersionNotDraft("not_draft")
    files = store.list_version_files(version_record["id"])
    if not any(f.get("id") == file_id for f in files):
        raise VersionFileNotFound(f"file {file_id} not found")
    store.delete_version_file(file_id)


class AgentNotFound(LookupError):
    def __init__(self, agent_id: str) -> None:
        super().__init__(f"unknown agent {agent_id!r}")
        self.agent_id = agent_id


def require_agent_exists(agent_id: str, *, store: SessionStore) -> None:
    if store.get_agent_def(agent_id) is not None:
        return
    raise AgentNotFound(agent_id)
