"""AgentService — the agent-domain public service object.

Stateful: the ``Database`` (managers) is resolved internally by ``Service``
from settings — never passed in. Methods take only their domain arguments,
never ``db`` or ``store``. This is the agent slice of the manager migration
that plan 064_03 left unfinished: logic lives on the managers, this object
is the surface.

    svc = AgentService()
    svc.soft_delete("my-agent")

ponytail: increment 1 exposes the meta/lifecycle/comments/ratings cluster.
Remaining surface (versions, prompts, grants, sync) is added as those
mixins are ported off ``SessionStore``.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import logging
import uuid
from typing import Any, cast

from agentbox.core.agents.composition.drift import _build_config_json, _build_snapshot
from agentbox.core.agents.composition.preview import (
    PreviewError as PreviewError,
    render_agent_prompt_preview as _render_agent_prompt_preview,
)
from agentbox.core.agents.config import build_config_json_payload
from agentbox.core.config import load_settings
from agentbox.core.constants import SessionMode
from agentbox.core.data import (
    AgentConfigEventRow,
    AgentDef,
    AgentMetaRow,
    AgentSyncRow,
    AgentToolGrantRow,
    AgentVersionCommentRow,
    AgentVersionFileRow,
    AgentVersionRatingRow,
    AgentVersionRow,
    PromptVersionRow,
    VersionFileUploadRow,
    _AgentMetaPatchFields,
    _AgentSyncPatchFields,
    _AgentToolGrantPatchFields,
    _AgentVersionFields,
)
from agentbox.core.data._util import now_iso
from agentbox.core.service.agents.crud import (
    get_agent_detail as _get_agent_detail_free,
    list_agents_enriched as _list_agents_enriched_free,
)
from agentbox.core.service.agents.prompt.patch import (
    AgentServiceError as AgentServiceError,
    _apply_patch_to_agent,
    _validate_runner_against_registry,
    decode_config_json as _decode_config_json_free,
)
from agentbox.core.service.agents.prompt.validation import (
    _validators_view,
    normalize_validator_entries as _normalize_validator_entries_free,
)
from agentbox.core.service.agents.versions import (
    AgentAlreadyExists as AgentAlreadyExists,
    AgentNotFound as AgentNotFound,
    DuplicateVersionFile as DuplicateVersionFile,
    VersionFileNotFound as VersionFileNotFound,
    VersionNotDraft as VersionNotDraft,
    VersionNotFound as VersionNotFound,
)
from agentbox.core.service.base import Service

logger = logging.getLogger(__name__)

_VALID_FILE_KINDS = {
    "system",
    "user_template",
    "reference",
    "output_schema",
    "input_schema",
    "other",
}


def _config_hash(config_json: dict) -> str:
    return hashlib.sha256(
        json.dumps(config_json, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _prepare_files(files: list[dict]) -> list[dict]:
    """Validate + normalize file rows (dedupe, kind check, sha256, position)."""
    prepared: list[dict] = []
    seen: set[str] = set()
    for i, f in enumerate(files):
        relative_path = f.get("relative_path")
        if not relative_path:
            raise ValueError("file row missing 'relative_path'")
        if relative_path in seen:
            raise ValueError(f"duplicate relative_path in files: {relative_path}")
        seen.add(relative_path)
        kind = f.get("kind", "other")
        if kind not in _VALID_FILE_KINDS:
            raise ValueError(
                f"invalid file kind {kind!r}; expected one of {sorted(_VALID_FILE_KINDS)}"
            )
        content = f.get("content", "")
        if content is None:
            content = ""
        sha256 = f.get("sha256") or _hash_content(content)
        prepared.append(
            {
                "relative_path": relative_path,
                "kind": kind,
                "content": content,
                "sha256": sha256,
                "source_uri": f.get("source_uri"),
                "position": int(f.get("position", i)),
            }
        )
    return prepared


def _text_diff(a: str, b: str) -> str:
    if a == b:
        return ""
    return "".join(
        difflib.unified_diff(a.splitlines(keepends=True), b.splitlines(keepends=True), lineterm="")
    )


def _json_diff(a: str, b: str) -> dict:
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


class AgentService(Service):
    """Agent lifecycle + feedback — policy over the db managers.

    Managers only touch tables; this object owns the rules: existence
    guards, timestamps, upsert branching, active-pointer clearing, and
    rating bounds.
    """

    def __init__(self) -> None:
        super().__init__()
        self._meta = self._db.agent_meta
        self._versions = self._db.agent_versions
        self._active = self._db.active_agent_versions
        self._comments = self._db.agent_version_comments
        self._ratings = self._db.agent_version_ratings
        self._grants = self._db.agent_tool_grants
        self._files = self._db.agent_version_files
        self._prompts = self._db.prompt_versions
        self._sync = self._db.agent_sync
        self._events = self._db.agent_config_events

    # ── lifecycle ──────────────────────────────────────────────────────
    def get_meta(self, agent_id: str) -> AgentMetaRow | None:
        return self._meta.get_meta(agent_id)

    def is_deleted(self, agent_id: str) -> bool:
        meta = self._meta.get_meta(agent_id)
        return bool(meta and meta.get("deleted_at"))

    def is_disabled(self, agent_id: str) -> bool:
        meta = self._meta.get_meta(agent_id)
        return bool(meta and meta.get("disabled_at"))

    # ── version reads ──────────────────────────────────────────────────
    def latest_version(self, agent_id: str) -> AgentVersionRow | None:
        return self._versions.get_latest(agent_id)

    def active_version(self, agent_id: str) -> AgentVersionRow | None:
        return self._versions.get_active(agent_id)

    def get_version(self, agent_id: str, version: int) -> AgentVersionRow | None:
        return self._versions.get_by_number(agent_id, version)

    def get_version_by_id(self, version_id: int) -> AgentVersionRow | None:
        return self._versions.get_by_id(version_id)

    def list_versions(self, agent_id: str) -> list[AgentVersionRow]:
        return self._versions.list_for_agent(agent_id)

    def diff_versions(self, agent_id: str, a: int, b: int) -> dict:
        """Diff two versions' prompt + config snapshots. Raises if either missing."""
        va = self.get_version(agent_id, a)
        vb = self.get_version(agent_id, b)
        if va is None or vb is None:
            raise ValueError(f"version not found: {a if va is None else b}")
        return {
            "from_version": a,
            "to_version": b,
            "prompt_diff": _text_diff(va["prompt_snapshot"], vb["prompt_snapshot"]),
            "content_diff": _json_diff(va["content_snapshot"], vb["content_snapshot"]),
        }

    def _stamp(self, agent_id: str, column: str) -> AgentMetaRow | None:
        """Set a timestamp column, inserting the meta row if absent.

        None when the agent has no version history. Backs ``soft_delete``
        (deleted_at, also clears the active pointer) and ``disable``.
        """
        if not self._versions.exists_for_agent(agent_id):
            return None
        now = now_iso()
        if self._meta.get_meta(agent_id) is not None:
            self._meta.patch(agent_id, **cast(_AgentMetaPatchFields, {column: now, "updated_at": now}))
        else:
            self._meta.insert(
                agent_id=agent_id,
                sync_mode="off",
                export_to_disk=0,
                source_path=None,
                source_format=None,
                created_at=now,
                updated_at=now,
                **cast(Any, {column: now}),  # type: ignore[reportCallIssue] — dynamic column name
            )
        if column == "deleted_at":
            self._active.delete_for_agent(agent_id)
        return self._meta.get_meta(agent_id)

    def _clear(self, agent_id: str, column: str) -> AgentMetaRow | None:
        """Clear a timestamp column (restore/enable). None if no meta row."""
        if self._meta.get_meta(agent_id) is None:
            return None
        self._meta.patch(agent_id, **cast(_AgentMetaPatchFields, {column: None, "updated_at": now_iso()}))
        return self._meta.get_meta(agent_id)

    def soft_delete(self, agent_id: str) -> AgentMetaRow | None:
        """Mark deleted (stamp deleted_at, clear active pointer). Idempotent."""
        return self._stamp(agent_id, "deleted_at")

    def restore(self, agent_id: str) -> AgentMetaRow | None:
        """Clear deleted_at. Active pointer must be re-set separately."""
        return self._clear(agent_id, "deleted_at")

    def disable(self, agent_id: str) -> AgentMetaRow | None:
        """Stamp disabled_at — visible but un-invokable. Keeps active pointer."""
        return self._stamp(agent_id, "disabled_at")

    def enable(self, agent_id: str) -> AgentMetaRow | None:
        """Clear disabled_at."""
        return self._clear(agent_id, "disabled_at")

    def update_meta(
        self,
        agent_id: str,
        *,
        sync_mode: str | None = None,
        export_to_disk: bool | None = None,
        source_path: str | None = None,
        source_format: str | None = None,
    ) -> AgentMetaRow | None:
        """Patch supplied meta fields. None if the agent has no meta row."""
        if self._meta.get_meta(agent_id) is None:
            return None
        values: _AgentMetaPatchFields = {"updated_at": now_iso()}
        if sync_mode is not None:
            values["sync_mode"] = sync_mode
        if export_to_disk is not None:
            values["export_to_disk"] = int(export_to_disk)
        if source_path is not None:
            values["source_path"] = source_path
        if source_format is not None:
            values["source_format"] = source_format
        self._meta.patch(agent_id, **values)
        return self._meta.get_meta(agent_id)

    # ── feedback ───────────────────────────────────────────────────────
    def add_comment(self, version_id: int, author: str, body: str) -> AgentVersionCommentRow:
        self._comments.insert(
            version_id=version_id, author=author, body=body, created_at=now_iso()
        )
        comment = self._comments.latest_for_version(version_id)
        assert comment is not None
        return comment

    def list_comments(self, version_id: int) -> list[AgentVersionCommentRow]:
        return self._comments.list_for_version(version_id)

    def set_rating(self, version_id: int, rating: int, rater: str) -> AgentVersionRatingRow:
        if not (1 <= rating <= 5):
            raise ValueError(f"rating must be 1-5, got {rating}")
        self._ratings.insert(
            version_id=version_id, rating=rating, rater=rater, rated_at=now_iso()
        )
        result = self._ratings.latest_for_version(version_id)
        assert result is not None
        return result

    def get_rating(self, version_id: int) -> AgentVersionRatingRow | None:
        return self._ratings.latest_for_version(version_id)

    # ── version writes ─────────────────────────────────────────────────
    def _refresh_meta_on_write(
        self,
        agent_id: str,
        *,
        sync_mode: str,
        export_to_disk: bool,
        source_path: str | None,
        source_format: str | None,
        clear_deleted: bool,
    ) -> None:
        """Upsert agent_meta alongside a version write.

        ponytail: run as its own transaction, separate from the version
        insert — a crash between them leaves a version without meta, which
        is self-healing (meta is auxiliary, re-created on next write). Give
        Manager a shared-transaction API if that window ever matters.
        """
        now = now_iso()
        if self._meta.get_meta(agent_id) is not None:
            values: _AgentMetaPatchFields = {
                "sync_mode": sync_mode,
                "export_to_disk": int(export_to_disk),
                "source_path": source_path,
                "source_format": source_format,
                "updated_at": now,
            }
            if clear_deleted:
                values["deleted_at"] = None
            self._meta.patch(agent_id, **values)
        else:
            self._meta.insert(
                agent_id=agent_id,
                sync_mode=sync_mode,
                export_to_disk=int(export_to_disk),
                source_path=source_path,
                source_format=source_format,
                created_at=now,
                updated_at=now,
            )

    def create_agent(
        self,
        agent_id: str,
        config_json: dict,
        *,
        prompt_content: str | None = None,
        author: str,
        changelog: str,
        source: str = "ui",
        source_path: str | None = None,
        source_format: str | None = None,
        sync_mode: str = "off",
        export_to_disk: bool = False,
    ) -> AgentVersionRow:
        """Create a new agent with its v1 draft + agent_meta row."""
        if self._versions.exists_for_agent(agent_id):
            raise ValueError(f"Agent {agent_id!r} already exists")
        vid = self._versions.insert_version(
            agent_id=agent_id,
            version=1,
            source_path=source_path or "",
            source_format=source_format or "",
            content_snapshot="",
            prompt_snapshot="",
            content_hash=_config_hash(config_json),
            author=author,
            changelog=changelog,
            is_legacy=0,
            created_at=now_iso(),
            config_json=json.dumps(config_json, sort_keys=True),
            prompt_content=prompt_content,
            source=source,
        )
        self._refresh_meta_on_write(
            agent_id,
            sync_mode=sync_mode,
            export_to_disk=export_to_disk,
            source_path=source_path,
            source_format=source_format,
            clear_deleted=False,
        )
        result = self._versions.get_by_id(vid)
        assert result is not None, f"version {vid} not found after insert for agent {agent_id!r}"
        return result

    def add_agent_version(
        self,
        agent_id: str,
        config_json: dict,
        *,
        prompt_content: str | None = None,
        author: str,
        changelog: str,
        source: str = "ui",
        source_path: str | None = None,
        source_format: str | None = None,
        sync_mode: str = "off",
        export_to_disk: bool = False,
    ) -> AgentVersionRow:
        """Append a new draft version. No existence check; clears deleted_at."""
        latest = self._versions.get_latest(agent_id)
        next_version = (latest.get("version") or 0) + 1 if latest else 1
        vid = self._versions.insert_version(
            agent_id=agent_id,
            version=next_version,
            source_path=source_path or "",
            source_format=source_format or "",
            content_snapshot="",
            prompt_snapshot="",
            content_hash=_config_hash(config_json),
            author=author,
            changelog=changelog,
            is_legacy=0,
            created_at=now_iso(),
            config_json=json.dumps(config_json, sort_keys=True),
            prompt_content=prompt_content,
            source=source,
        )
        self._refresh_meta_on_write(
            agent_id,
            sync_mode=sync_mode,
            export_to_disk=export_to_disk,
            source_path=source_path,
            source_format=source_format,
            clear_deleted=True,
        )
        result = self._versions.get_by_id(vid)
        assert result is not None, f"version {vid} not found after insert for agent {agent_id!r}"
        return result

    def publish_version(self, agent_id: str, version: int, reason: str) -> AgentVersionRow:
        """Activate a version; append reason to changelog, snapshot grants."""
        if not reason or len(reason) < 3:
            raise ValueError("reason must be at least 3 characters")
        row = self._versions.get_by_number(agent_id, version)
        if row is None:
            raise ValueError(f"version {version} not found for agent {agent_id}")
        version_id = row["id"]
        old = row.get("changelog") or ""
        values: _AgentVersionFields = {
            "changelog": f"{old}\n\npublish: {reason}" if old else reason
        }
        try:
            values["resolved_tool_grants"] = sorted(self.active_grants(agent_id))
        except Exception:
            logger.warning(
                "publish_version: failed to snapshot tool grants for agent %r v%d",
                agent_id,
                version,
                exc_info=True,
            )
        self._versions.patch(version_id, **values)
        self._active.set_pointer(agent_id, version_id, now_iso())
        result = self._versions.get_by_number(agent_id, version)
        assert result is not None, f"version {version} not found after publish for agent {agent_id!r}"
        return result

    def rollback_to(
        self, agent_id: str, target_version: int, reason: str, *, author: str
    ) -> AgentVersionRow:
        """Create + activate a new version cloned from ``target_version``."""
        if not reason or len(reason) < 3:
            raise ValueError("reason must be at least 3 characters")
        target = self._versions.get_by_number(agent_id, target_version)
        if target is None:
            raise ValueError(
                f"target_version {target_version} not found for agent {agent_id}"
            )
        latest = self._versions.get_latest(agent_id)
        next_v = (latest.get("version") or 0) + 1 if latest else 1
        new_vid = self._versions.insert_version(
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
        self._active.set_pointer(agent_id, new_vid, now_iso())
        result = self._versions.get_by_id(new_vid)
        assert result is not None, f"version {new_vid} not found after rollback for agent {agent_id!r}"
        return result

    # ── tool grants ────────────────────────────────────────────────────
    def grant_tool(
        self, agent_id: str, tool_name: str, changelog: str, actor: str | None = None
    ) -> AgentToolGrantRow:
        """Grant a tool, reactivating a previously-revoked grant if present."""
        if len(changelog.strip()) < 3:
            raise ValueError("changelog must be at least 3 characters")
        now = now_iso()
        fields: _AgentToolGrantPatchFields = {
            "changelog": changelog,
            "granted_at": now,
            "granted_by": actor,
            "revoked_at": None,
            "revoked_by": None,
            "revoke_changelog": None,
        }
        existing = self._grants.get_grant(agent_id, tool_name)
        if existing is None:
            self._grants.insert(
                id=str(uuid.uuid4()), agent_id=agent_id, tool_name=tool_name, **fields
            )
        else:
            self._grants.update_by_id(existing["id"], **fields)
        row = self._grants.get_grant(agent_id, tool_name)
        assert row is not None
        return row

    def revoke_tool(
        self, agent_id: str, tool_name: str, changelog: str, actor: str | None = None
    ) -> None:
        """Soft-revoke an active grant. Raises if no active grant exists."""
        if len(changelog.strip()) < 3:
            raise ValueError("changelog must be at least 3 characters")
        affected = self._grants.revoke_active(
            agent_id, tool_name, revoked_at=now_iso(), revoked_by=actor, revoke_changelog=changelog
        )
        if affected == 0:
            raise ValueError(f"No active grant for agent {agent_id!r} / tool {tool_name!r}")

    def list_tool_grants(self, agent_id: str, include_revoked: bool = False) -> list[AgentToolGrantRow]:
        return self._grants.list_for_agent(agent_id, include_revoked=include_revoked)

    def active_grants(self, agent_id: str) -> set[str]:
        """Set of active tool names — used by the executor at run-start."""
        return {r["tool_name"] for r in self._grants.list_for_agent(agent_id)}

    # ── prompts ────────────────────────────────────────────────────────
    def list_prompt_versions(self, agent_id: str) -> list[PromptVersionRow]:
        return self._prompts.list_for_agent(agent_id)

    def get_prompt_version(self, agent_id: str, version: int) -> PromptVersionRow | None:
        return self._prompts.get_by_number(agent_id, version)

    def get_latest_committed_prompt(self, agent_id: str) -> PromptVersionRow | None:
        return self._prompts.get_latest_committed(agent_id)

    def get_prompt_draft(self, agent_id: str) -> PromptVersionRow | None:
        return self._prompts.get_draft(agent_id)

    def save_prompt_draft(
        self, agent_id: str, content: str, author: str = "system"
    ) -> PromptVersionRow:
        """Save or replace the agent's single prompt draft."""
        return self._prompts.replace_draft(
            agent_id,
            content=content,
            content_hash=_hash_content(content),
            author=author,
            changelog="",
            created_at=now_iso(),
        )

    def publish_prompt(
        self, agent_id: str, changelog: str = "", author: str = "system"
    ) -> PromptVersionRow:
        """Commit the current draft as a published version. Raises if none."""
        draft = self._prompts.get_draft(agent_id)
        if not draft:
            raise ValueError(f"No draft found for agent {agent_id!r}")
        self._prompts.patch(
            draft["id"], is_draft=0, changelog=changelog, created_at=now_iso()
        )
        result = self._prompts.get_by_number(agent_id, draft["version"])
        assert result is not None, f"prompt version {draft['version']} not found after publish for agent {agent_id!r}"
        return result

    def rollback_prompt(
        self, agent_id: str, target_version: int, author: str = "system"
    ) -> PromptVersionRow:
        """Commit a new version copying ``target_version``'s content."""
        target = self._prompts.get_by_number(agent_id, target_version)
        if not target:
            raise ValueError(
                f"Version {target_version} not found for agent {agent_id!r}"
            )
        if target["is_draft"]:
            raise ValueError(f"Cannot rollback to a draft version ({target_version})")
        return self._prompts.insert_committed(
            agent_id,
            content=target["content"],
            content_hash=_hash_content(target["content"]),
            author=author,
            changelog=f"Rollback to version {target_version}",
            created_at=now_iso(),
            delete_drafts=True,
        )

    def sync_prompt_from_disk(
        self,
        agent_id: str,
        content: str,
        author: str = "filesystem",
        changelog: str | None = None,
    ) -> PromptVersionRow | None:
        """Capture an on-disk prompt as a committed version if it changed.

        Returns ``None`` (leaving the DB untouched) when the content matches
        the latest committed version by hash.
        """
        new_hash = _hash_content(content)
        latest = self._prompts.get_latest_committed(agent_id)
        if latest is not None:
            existing_hash = latest.get("content_hash") or _hash_content(
                latest["content"]
            )
            if existing_hash == new_hash:
                return None
            default_changelog = "Out-of-band file edit"
        else:
            default_changelog = "Imported from disk"
        return self._prompts.insert_committed(
            agent_id,
            content=content,
            content_hash=new_hash,
            author=author,
            changelog=changelog if changelog is not None else default_changelog,
            created_at=now_iso(),
            delete_drafts=False,
        )

    # ── sync metadata ──────────────────────────────────────────────────
    def get_agent_sync(self, agent_id: str) -> AgentSyncRow | None:
        return self._sync.get_row(agent_id)

    def upsert_agent_sync(
        self,
        agent_id: str,
        proxy_path: str | None = None,
        sync_mode: str | None = None,
        sync_policy: str | None = None,
        last_file_hash: str | None = None,
        last_file_mtime: str | None = None,
    ) -> AgentSyncRow:
        """Insert or patch the sync row. Only supplied fields are updated.

        ponytail: read-then-insert/patch is not one transaction — a race
        loses a concurrent write, but agent_sync is auxiliary bookkeeping
        (last-write-wins is fine), same window the meta upsert accepts.
        """
        now = now_iso()
        if self._sync.get_row(agent_id) is None:
            self._sync.insert(
                agent_id=agent_id,
                proxy_path=proxy_path,
                sync_mode=sync_mode or "manual",
                sync_policy=sync_policy or "db_wins",
                last_file_hash=last_file_hash,
                last_file_mtime=last_file_mtime,
                last_sync_at=now,
            )
        else:
            values: _AgentSyncPatchFields = {"last_sync_at": now}
            if proxy_path is not None:
                values["proxy_path"] = proxy_path
            if sync_mode is not None:
                values["sync_mode"] = sync_mode
            if sync_policy is not None:
                values["sync_policy"] = sync_policy
            if last_file_hash is not None:
                values["last_file_hash"] = last_file_hash
            if last_file_mtime is not None:
                values["last_file_mtime"] = last_file_mtime
            self._sync.patch(agent_id, **values)
        result = self._sync.get_row(agent_id)
        assert result is not None, f"sync row not found after upsert for agent {agent_id!r}"
        return result

    def delete_agent_sync(self, agent_id: str) -> None:
        self._sync.delete_for_agent(agent_id)

    # ── config events ──────────────────────────────────────────────────
    def record_config_event(
        self,
        agent_id: str,
        field: str,
        from_value: object,
        to_value: object,
        author: str = "api",
        source: str = "api:patch",
    ) -> AgentConfigEventRow:
        """Append a non-versioned config-change audit row."""
        event_id = self._events.insert(
            agent_id=agent_id,
            field=field,
            from_value=json.dumps(from_value) if from_value is not None else None,
            to_value=json.dumps(to_value) if to_value is not None else None,
            author=author,
            source=source,
            created_at=now_iso(),
        )
        result = self._events.get_by_id(event_id)
        assert result is not None, f"config event {event_id} not found after insert for agent {agent_id!r}"
        return result

    def list_config_events(self, agent_id: str, limit: int = 50) -> list[AgentConfigEventRow]:
        return self._events.list_for_agent(agent_id, limit=limit)

    # ── version files ──────────────────────────────────────────────────
    def create_version(
        self,
        agent_id: str,
        source_path: str,
        source_format: str,
        content_snapshot: str,
        prompt_snapshot: str,
        content_hash: str,
        author: str = "system",
        changelog: str = "",
        is_legacy: bool = False,
        files: list[dict] | None = None,
        config_json: str | None = None,
        prompt_content: str | None = None,
        source: str = "manifest",
    ) -> AgentVersionRow:
        """Insert a fully-specified version (+ its files) atomically."""
        prepared = _prepare_files(files) if files else []
        vid = self._versions.insert_version(
            files=prepared or None,
            agent_id=agent_id,
            version=self._versions.next_version(agent_id),
            source_path=source_path,
            source_format=source_format,
            content_snapshot=content_snapshot,
            prompt_snapshot=prompt_snapshot,
            content_hash=content_hash,
            author=author,
            changelog=changelog,
            is_legacy=int(is_legacy),
            created_at=now_iso(),
            config_json=config_json,
            prompt_content=prompt_content,
            source=source,
        )
        result = self._versions.get_by_id(vid)
        assert result is not None, f"version {vid} not found after insert for agent {agent_id!r}"
        return result

    def list_version_files(self, version_id: int) -> list[AgentVersionFileRow]:
        return self._files.list_for_version(version_id)

    def insert_version_files(self, version_id: int, files: list[dict]) -> None:
        prepared = _prepare_files(files)
        if prepared:
            self._files.insert_files(version_id, prepared)

    def replace_version_files(self, version_id: int, files: list[dict]) -> None:
        self._files.replace_files(version_id, _prepare_files(files) if files else [])

    def delete_version_files(self, version_id: int) -> None:
        self._files.delete_for_version(version_id)

    def delete_version_file(self, file_id: int) -> None:
        self._files.delete_file(file_id)

    def replace_version_config(self, version_id: int, config_json: str) -> None:
        """Overwrite a version's config_json in-place (migration path)."""
        self._versions.patch(version_id, config_json=config_json)

    def activate_version(self, agent_id: str, version_id: int) -> None:
        """Pin ``version_id`` as the active version for ``agent_id``."""
        self._active.set_pointer(agent_id, version_id, now_iso())

    # ── revisions (clone-from-active writes) ───────────────────────────
    def branch_draft(self, agent_id: str, *, author: str) -> AgentVersionRow:
        """Clone the active version into a new (inactive) version."""
        active = self.active_version(agent_id)
        if active is None:
            raise ValueError(f"No active version for agent {agent_id}")
        vid = self._versions.insert_version(
            copy_files_from=active["id"],
            agent_id=agent_id,
            version=self._versions.next_version(agent_id),
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
        result = self._versions.get_by_id(vid)
        assert result is not None, f"version {vid} not found after branch_draft for agent {agent_id!r}"
        return result

    def save_prompt_revision(
        self,
        agent_id: str,
        *,
        prompt_content: str,
        author: str,
        changelog: str = "",
        activate: bool = False,
    ) -> AgentVersionRow:
        """New version cloning active config but with a fresh prompt."""
        active = self.active_version(agent_id) or self.latest_version(agent_id)
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
        vid = self._versions.insert_version(
            copy_files_from=active["id"],
            activate_for=agent_id if activate else None,
            activated_at=now_iso() if activate else None,
            agent_id=agent_id,
            version=self._versions.next_version(agent_id),
            source_path=active.get("source_path") or "",
            source_format=active.get("source_format") or "",
            content_snapshot=active.get("content_snapshot") or "",
            prompt_snapshot=prompt_content,
            content_hash="",
            author=author,
            changelog=changelog or f"prompt edit from v{active['version']}",
            is_legacy=0,
            created_at=now_iso(),
            config_json=cloned_config,
            prompt_content=prompt_content,
            source=active.get("source", "ui"),
        )
        result = self._versions.get_by_id(vid)
        assert result is not None, f"version {vid} not found after save_prompt_revision for agent {agent_id!r}"
        return result

    def save_config_revision(
        self,
        agent_id: str,
        *,
        config_patch: dict,
        author: str,
        changelog: str = "",
        activate: bool = True,
    ) -> AgentVersionRow:
        """New version with config_json shallow-merged from ``config_patch``."""
        active = self.active_version(agent_id) or self.latest_version(agent_id)
        if active is None:
            raise ValueError(f"No version to clone for agent {agent_id}")
        raw = active.get("config_json")
        try:
            current_cfg = (
                json.loads(raw) if isinstance(raw, str) and raw else (raw or {})
            )
        except (ValueError, TypeError):
            current_cfg = {}
        if not isinstance(current_cfg, dict):
            current_cfg = {}
        merged = {**current_cfg, **(config_patch or {})}
        new_config_str = json.dumps(merged, sort_keys=True)
        vid = self._versions.insert_version(
            copy_files_from=active["id"],
            activate_for=agent_id if activate else None,
            activated_at=now_iso() if activate else None,
            agent_id=agent_id,
            version=self._versions.next_version(agent_id),
            source_path=active.get("source_path") or "",
            source_format=active.get("source_format") or "",
            content_snapshot=active.get("content_snapshot") or "",
            prompt_snapshot=active.get("prompt_snapshot") or "",
            content_hash=hashlib.sha256(new_config_str.encode("utf-8")).hexdigest(),
            author=author,
            changelog=changelog or f"config edit from v{active['version']}",
            is_legacy=0,
            created_at=now_iso(),
            config_json=new_config_str,
            prompt_content=active.get("prompt_content"),
            source=active.get("source", "ui"),
        )
        result = self._versions.get_by_id(vid)
        assert result is not None, f"version {vid} not found after save_config_revision for agent {agent_id!r}"
        return result

    # ── resolution reads ───────────────────────────────────────────────
    def list_agents_with_latest(
        self,
        include_deleted: bool = False,
        include_disabled: bool = False,
    ) -> list[AgentVersionRow]:
        """Latest-version snapshot per agent, honoring deleted/disabled flags."""
        rows = self._versions.list_latest_per_agent()
        if include_deleted and include_disabled:
            return rows
        hidden: set[str] = set()
        if not include_deleted:
            hidden |= self._meta.agent_ids_with_deleted()
        if not include_disabled:
            hidden |= self._meta.agent_ids_with_disabled()
        return [r for r in rows if r.get("agent_id") not in hidden]

    def get_agent_def(self, agent_id: str) -> AgentDef | None:
        """Reconstruct an ``AgentDef`` from the active (else latest) version.

        Returns ``None`` when the agent has no usable version, is soft-deleted,
        or the stored snapshot fails validation.
        """
        row = self.active_version(agent_id) or self.latest_version(agent_id)
        if row is None:
            return None
        if self.is_deleted(agent_id):
            return None
        try:
            return AgentDef.from_db_row(row)
        except ValueError:
            return None
        except Exception as exc:
            logger.warning(
                "get_agent_def: row for %r v%s failed validation: %s",
                agent_id,
                row.get("version"),
                exc,
            )
            return None

    def resolve_agent(self, agent_id: str) -> AgentDef | None:
        """Active-else-latest ``AgentDef`` or ``None`` (alias of get_agent_def)."""
        return self.get_agent_def(agent_id)

    def render_agent_prompt_preview(
        self,
        *,
        agent_id: str,
        template: str,
        bindings_override: list[dict] | None = None,
    ) -> dict:
        """Render the composed prompt preview for an agent.

        Thin delegator to the free-function in ``core.agents.composition.preview``.
        Raises ``PreviewError`` when a binding cannot be resolved.
        """
        return _render_agent_prompt_preview(
            self._versions,
            self._db.resource_versions,
            self._db.resource_blobs,
            self._db.resources,
            self._db.agent_prompt_resource_bindings,
            agent_id=agent_id,
            template=template,
            bindings_override=bindings_override,
        )

    def require_agent_exists(self, agent_id: str) -> None:
        """Raise ``AgentNotFound`` when the agent has no usable version."""
        if self.get_agent_def(agent_id) is not None:
            return
        raise AgentNotFound(agent_id)

    def list_all_agents(self, include_disabled: bool = False) -> list[AgentDef]:
        """Latest-version ``AgentDef`` per agent, skipping unparseable rows."""
        out: list[AgentDef] = []
        for row in self.list_agents_with_latest(include_disabled=include_disabled):
            try:
                agent = AgentDef.from_db_row(row)
            except ValueError:
                continue
            except Exception:
                logger.exception(
                    "list_all_agents: snapshot for %r v%s failed validation",
                    row.get("agent_id"),
                    row.get("version"),
                )
                continue
            out.append(agent)
        return out

    # ── agent creation + version files (orchestration) ─────────────────
    def create_agent_record(
        self,
        *,
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
        """Create (or, if soft-deleted, re-version) an agent from a request.

        Raises ``AgentAlreadyExists`` when a live agent with this id exists.
        """
        agent_def = AgentDef(
            id=agent_id,
            description=description,
            runner=runner,
            prompt=prompt,
            composition=composition,
            tools=tools or [],
            tags=tags or [],
            workspace=workspace,
            session_mode=session_mode or SessionMode.HEADLESS,
            webhook_url=webhook_url,
            source_path=None,
            source_format=None,
        )
        config_payload = {
            **agent_def.model_dump(mode="json", exclude_none=True),
            **build_config_json_payload(agent_def),
        }
        if self.is_deleted(agent_id):
            return self.add_agent_version(
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
        try:
            return self.create_agent(
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
        except ValueError as exc:
            raise AgentAlreadyExists(str(exc)) from exc

    def upload_version_file(
        self,
        *,
        agent_id: str,
        version: int,
        kind: str,
        name: str,
        content: str,
    ) -> VersionFileUploadRow:
        """Attach a file to a draft (non-active) version. Guards + dedupes."""
        version_record = self.get_version(agent_id, version)
        if version_record is None:
            raise VersionNotFound(f"version {version} not found")
        active = self.active_version(agent_id)
        if active is not None and active["id"] == version_record["id"]:
            raise VersionNotDraft("cannot modify active version")

        sha256_hash = hashlib.sha256(content.encode()).hexdigest()
        files = self.list_version_files(version_record["id"])
        for f in files:
            if f.get("sha256") == sha256_hash:
                raise DuplicateVersionFile("duplicate_sha256")
            if f.get("relative_path") == name:
                raise DuplicateVersionFile("duplicate_path")

        self.insert_version_files(
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
        files = self.list_version_files(version_record["id"])
        inserted = next((f for f in files if f.get("sha256") == sha256_hash), None)
        if inserted is None:
            raise RuntimeError("file_insert_failed")
        return VersionFileUploadRow(file=inserted, sha256=sha256_hash, size=len(content))

    def remove_version_file(
        self,
        *,
        agent_id: str,
        version: int,
        file_id: int,
    ) -> None:
        """Delete a file from a draft (non-active) version. Guards existence.

        ponytail: distinct name from ``delete_version_file(file_id)`` (the
        unguarded manager passthrough) to avoid clobbering that method.
        """
        version_record = self.get_version(agent_id, version)
        if version_record is None:
            raise VersionNotFound(f"version {version} not found")
        active = self.active_version(agent_id)
        if active is not None and active["id"] == version_record["id"]:
            raise VersionNotDraft("not_draft")
        files = self.list_version_files(version_record["id"])
        if not any(f.get("id") == file_id for f in files):
            raise VersionFileNotFound(f"file {file_id} not found")
        self.delete_version_file(file_id)

    def update_agent_meta(
        self,
        agent_id: str,
        *,
        sync_mode: str | None = None,
        export_to_disk: bool | None = None,
        source_path: str | None = None,
        source_format: str | None = None,
    ) -> AgentMetaRow | None:
        """Update agent metadata fields (alias of ``update_meta``)."""
        return self.update_meta(
            agent_id,
            sync_mode=sync_mode,
            export_to_disk=export_to_disk,
            source_path=source_path,
            source_format=source_format,
        )

    # ── config patch + validation ──────────────────────────────────────
    @staticmethod
    def decode_config_json(raw: Any) -> dict:
        """Best-effort decode of a stored ``config_json`` blob to a dict."""
        return _decode_config_json_free(raw)

    def patch_agent_config(
        self, agent_id: str, patch: dict, *, settings: Any = None
    ) -> AgentDef:
        """Merge ``patch`` onto the active def, mint + activate a new version.

        Raises ``AgentServiceError`` (HTTP-shaped) on any failure.
        """
        if settings is None:
            settings = load_settings()
        if not patch:
            raise AgentServiceError(400, "empty_patch", "empty patch")

        current = self.resolve_agent(agent_id)
        if current is None:
            raise AgentServiceError(404, "unknown_agent", agent_id)

        merged = _apply_patch_to_agent(current.model_dump(mode="python"), patch)
        try:
            updated = AgentDef.model_validate(merged)
        except Exception as exc:
            raise AgentServiceError(400, "validation_failed", str(exc)) from exc
        _validate_runner_against_registry(updated)
        updated.source_path = current.source_path
        updated.source_format = current.source_format

        prompt_text = ""
        if updated.prompt_path:
            try:
                prompt_text = updated.load_prompt(settings.project_root)
            except FileNotFoundError:
                prompt_text = ""
        snapshot = _build_snapshot(updated)
        config_json = _build_config_json(updated)

        active_row = self.active_version(agent_id)

        prior_cfg = self.decode_config_json((active_row or {}).get("config_json"))
        new_cfg = json.loads(config_json)
        for direction in ("input", "output"):
            prior_section = prior_cfg.get(direction)
            if not isinstance(prior_section, dict) or "validators" not in prior_section:
                continue
            section = new_cfg.get(direction)
            if not isinstance(section, dict):
                section = {}
            section.setdefault("validators", prior_section["validators"])
            new_cfg[direction] = section
        config_json = json.dumps(new_cfg)

        carried_prompt_content = (
            (active_row or {}).get("prompt_content") or prompt_text or None
        )
        carried_prompt_snapshot = (
            prompt_text or (active_row or {}).get("prompt_snapshot") or ""
        )

        try:
            new_version = self.create_version(
                agent_id=updated.id,
                source_path=str(updated.source_path) if updated.source_path else "",
                source_format=(
                    updated.source_format.value if updated.source_format else "unknown"
                ),
                content_snapshot=snapshot,
                prompt_snapshot=carried_prompt_snapshot,
                content_hash=hashlib.sha256(snapshot.encode("utf-8")).hexdigest(),
                author="api:patch",
                changelog=f"patch: {', '.join(sorted(patch))}",
                files=None,
                config_json=config_json,
                prompt_content=carried_prompt_content,
            )
        except Exception as exc:
            logger.exception("patch_agent_config: DB write failed for %r", agent_id)
            raise AgentServiceError(500, "db_write_failed", agent_id) from exc

        try:
            self.activate_version(updated.id, int(new_version["id"]))
        except Exception as exc:
            logger.exception(
                "patch_agent_config: activate_version failed for %r", agent_id
            )
            raise AgentServiceError(500, "activate_failed", agent_id) from exc

        self.upsert_agent_sync(
            agent_id=updated.id,
            proxy_path=str(updated.source_path) if updated.source_path else None,
        )

        return updated

    def normalize_validator_entries(
        self, direction: str, entries: list[dict]
    ) -> list[dict]:
        """Validate + canonicalize inline validator entries for a direction."""
        return _normalize_validator_entries_free(direction, entries)

    def get_agent_validation(self, agent_id: str) -> dict:
        """Read the active version's inline validators for both directions."""
        active = self.active_version(agent_id)
        if not active or active.get("id") is None:
            return {
                "agent_id": agent_id,
                "agent_version_id": None,
                "input": None,
                "output": None,
            }
        cfg = self.decode_config_json(active.get("config_json"))
        return {
            "agent_id": agent_id,
            "agent_version_id": int(active["id"]),
            "input": _validators_view(cfg, "input"),
            "output": _validators_view(cfg, "output"),
        }

    def put_agent_validation(
        self,
        agent_id: str,
        *,
        input_validators: list[dict] | None,
        output_validators: list[dict] | None,
        reason: str,
        actor: str | None,
        settings: Any = None,
    ) -> dict:
        """Write inline validators by minting + activating a new version."""
        if settings is None:
            settings = load_settings()
        current = self.resolve_agent(agent_id)
        if current is None:
            raise AgentServiceError(404, "unknown_agent", agent_id)

        explicit: dict[str, list[dict]] = {}
        if input_validators is not None:
            explicit["input"] = self.normalize_validator_entries(
                "input", input_validators
            )
        if output_validators is not None:
            explicit["output"] = self.normalize_validator_entries(
                "output", output_validators
            )
        if not explicit:
            raise AgentServiceError(
                400, "empty_validation_patch", "supply input and/or output"
            )

        active = self.active_version(current.id) or {}
        base_cfg = self.decode_config_json(active.get("config_json"))
        for direction, validators in explicit.items():
            section = base_cfg.get(direction)
            if not isinstance(section, dict):
                section = {}
            section["validators"] = validators
            base_cfg[direction] = section
        new_config_json = json.dumps(base_cfg)

        prompt_text = ""
        if current.prompt_path:
            try:
                prompt_text = current.load_prompt(settings.project_root)
            except FileNotFoundError:
                prompt_text = ""
        snapshot = _build_snapshot(current)
        carried_prompt_content = (
            active.get("prompt_content")
            or (current.prompt or "").strip()
            or prompt_text
            or None
        )

        try:
            new_version = self.create_version(
                agent_id=current.id,
                source_path=str(current.source_path) if current.source_path else "",
                source_format=(
                    current.source_format.value if current.source_format else "unknown"
                ),
                content_snapshot=snapshot,
                prompt_snapshot=prompt_text,
                content_hash=hashlib.sha256(snapshot.encode("utf-8")).hexdigest(),
                author=actor or "api:validation",
                changelog=f"validation: {reason}",
                files=None,
                config_json=new_config_json,
                prompt_content=carried_prompt_content,
            )
        except Exception as exc:
            logger.exception(
                "put_agent_validation: create_version failed for %r", agent_id
            )
            raise AgentServiceError(500, "db_write_failed", agent_id) from exc

        try:
            self.activate_version(current.id, int(new_version["id"]))
        except Exception as exc:
            logger.exception(
                "put_agent_validation: activate_version failed for %r", agent_id
            )
            raise AgentServiceError(500, "activate_failed", agent_id) from exc

        return self.get_agent_validation(agent_id)

    # ── enriched read views (cross-domain) ─────────────────────────────
    def list_agents_enriched(
        self, include_disabled: bool = False, *, settings: Any = None
    ) -> list[dict]:
        """Latest-version snapshot per agent enriched with run/profile/workspace."""
        return _list_agents_enriched_free(
            agent_versions=self._versions,
            agent_meta=self._meta,
            engine=self._db.engine,
            settings=settings or load_settings(),
            include_disabled=include_disabled,
        )

    def get_agent_detail(self, agent_id: str, *, settings: Any = None) -> dict | None:
        """Full agent detail (prompt, composition preview, versions, workspace)."""
        return _get_agent_detail_free(
            agent_id,
            agent_defs=self._db.agent_defs,
            agent_versions=self._versions,
            agent_meta=self._meta,
            agent_version_comments=self._comments,
            agent_version_ratings=self._ratings,
            resources=self._db.resources,
            resource_versions=self._db.resource_versions,
            resource_blobs=self._db.resource_blobs,
            agent_version_files=self._files,
            agent_prompt_resource_bindings=self._db.agent_prompt_resource_bindings,
            settings=settings or load_settings(),
        )
