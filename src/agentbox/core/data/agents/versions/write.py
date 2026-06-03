"""Agent-versions write operations.

Consolidated from write_agent.py, write_revisions.py, write_files.py,
write_meta.py during plan 27 modularization.
"""

from __future__ import annotations

import hashlib
import json
import logging

from sqlalchemy.engine import Engine

from agentbox.core.data.agents.grants import AgentToolGrantsMixin
from agentbox.core.data.agents.versions.models import _copy_version_files, _prepare_files
from agentbox.core.data.agents.versions.read import _AgentVersionsReadMixin
from agentbox.core.data.records import now_iso
from agentbox.core.data.schema import (
    active_agent_versions,
    agent_meta,
    agent_version_comments,
    agent_version_files,
    agent_version_ratings,
    agent_versions,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Agent lifecycle: create / publish / rollback
# ---------------------------------------------------------------------------


class _AgentVersionsAgentMixin(_AgentVersionsReadMixin, AgentToolGrantsMixin):
    """Create-agent, publish-version, rollback-to."""

    engine: Engine

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
    ) -> dict:
        """Create a new agent with its v1 draft and agent_meta row.

        Raises:
            ValueError: if agent_id already has versions.
        """
        existing = self.latest_version(agent_id)
        if existing is not None:
            raise ValueError(f"Agent {agent_id!r} already exists")

        content_hash = hashlib.sha256(
            json.dumps(config_json, sort_keys=True).encode("utf-8")
        ).hexdigest()
        config_str = json.dumps(config_json, sort_keys=True)

        with self.engine.begin() as conn:
            result = conn.execute(
                agent_versions.insert().values(
                    agent_id=agent_id,
                    version=1,
                    source_path=source_path or "",
                    source_format=source_format or "",
                    content_snapshot="",
                    prompt_snapshot="",
                    content_hash=content_hash,
                    author=author,
                    changelog=changelog,
                    is_legacy=0,
                    created_at=now_iso(),
                    config_json=config_str,
                    prompt_content=prompt_content,
                    source=source,
                    is_draft=1,
                )
            )
            pk = result.inserted_primary_key
            assert pk is not None
            version_id = int(pk[0])

            existing_meta = conn.execute(
                agent_meta.select().where(agent_meta.c.agent_id == agent_id)
            ).first()
            now = now_iso()
            if existing_meta:
                conn.execute(
                    agent_meta.update()
                    .where(agent_meta.c.agent_id == agent_id)
                    .values(
                        sync_mode=sync_mode,
                        export_to_disk=int(export_to_disk),
                        source_path=source_path,
                        source_format=source_format,
                        updated_at=now,
                    )
                )
            else:
                conn.execute(
                    agent_meta.insert().values(
                        agent_id=agent_id,
                        sync_mode=sync_mode,
                        export_to_disk=int(export_to_disk),
                        source_path=source_path,
                        source_format=source_format,
                        created_at=now,
                        updated_at=now,
                    )
                )

        return self.get_version_by_id(version_id) or {}

    def publish_version(self, agent_id: str, version: int, reason: str) -> dict:
        """Flip is_draft flag and set as active version.

        Raises:
            ValueError: if reason is empty or < 3 chars, or version not found.
        """
        if not reason or len(reason) < 3:
            raise ValueError("reason must be at least 3 characters")

        row = self._get_version_row(agent_id, version)
        if row is None:
            raise ValueError(f"version {version} not found for agent {agent_id}")

        version_id = row["id"]
        old_changelog = row.get("changelog") or ""
        new_changelog = (
            f"{old_changelog}\n\npublish: {reason}" if old_changelog else reason
        )

        with self.engine.begin() as conn:
            conn.execute(
                agent_versions.update()
                .where(agent_versions.c.id == version_id)
                .values(is_draft=0, changelog=new_changelog)
            )

            # Snapshot current active grants onto this version row
            try:
                active_grants = sorted(self.list_active_grants(agent_id))
                conn.execute(
                    agent_versions.update()
                    .where(agent_versions.c.id == version_id)
                    .values(resolved_tool_grants=active_grants)
                )
            except Exception:
                logger.warning(
                    "publish_version: failed to snapshot tool grants for agent %r v%d",
                    agent_id,
                    version,
                    exc_info=True,
                )

            conn.execute(
                active_agent_versions.delete().where(
                    active_agent_versions.c.agent_id == agent_id
                )
            )
            conn.execute(
                active_agent_versions.insert().values(
                    agent_id=agent_id,
                    version_id=version_id,
                    activated_at=now_iso(),
                )
            )

        return self.get_version(agent_id, version) or {}

    def rollback_to(
        self, agent_id: str, target_version: int, reason: str, *, author: str
    ) -> dict:
        """Create a new version rolling back to target_version's config.

        Raises:
            ValueError: if reason < 3 chars or target_version not found.
        """
        if not reason or len(reason) < 3:
            raise ValueError("reason must be at least 3 characters")

        target_row = self._get_version_row(agent_id, target_version)
        if target_row is None:
            raise ValueError(
                f"target_version {target_version} not found for agent {agent_id}"
            )

        next_v = self._next_version(agent_id)
        target_vid = target_row["id"]

        with self.engine.begin() as conn:
            result = conn.execute(
                agent_versions.insert().values(
                    agent_id=agent_id,
                    version=next_v,
                    source_path=target_row.get("source_path") or "",
                    source_format=target_row.get("source_format") or "",
                    content_snapshot=target_row.get("content_snapshot") or "",
                    prompt_snapshot=target_row.get("prompt_snapshot") or "",
                    content_hash=target_row.get("content_hash") or "",
                    author=author,
                    changelog=f"rollback to v{target_version}: {reason}",
                    is_legacy=0,
                    created_at=now_iso(),
                    config_json=target_row.get("config_json"),
                    prompt_content=target_row.get("prompt_content"),
                    source=target_row.get("source", "ui"),
                    is_draft=0,  # Rollbacks are immediately active
                )
            )
            pk = result.inserted_primary_key
            assert pk is not None
            new_vid = int(pk[0])
            _copy_version_files(conn, target_vid, new_vid)

            conn.execute(
                active_agent_versions.delete().where(
                    active_agent_versions.c.agent_id == agent_id
                )
            )
            conn.execute(
                active_agent_versions.insert().values(
                    agent_id=agent_id,
                    version_id=new_vid,
                    activated_at=now_iso(),
                )
            )

        return self.get_version_by_id(new_vid) or {}


# ---------------------------------------------------------------------------
# Revisions: branch drafts, prompt edits, config edits
# ---------------------------------------------------------------------------


class _AgentVersionsRevisionsMixin(_AgentVersionsReadMixin):
    """Clone-from-active version writes (drafts, prompt edits, config edits)."""

    engine: Engine

    def branch_draft(self, agent_id: str, *, author: str) -> dict:
        """Clone the active version into a new draft.

        Raises:
            ValueError: if no active version exists.
        """
        active = self.get_active_version(agent_id)
        if active is None:
            raise ValueError(f"No active version for agent {agent_id}")

        next_v = self._next_version(agent_id)
        active_vid = active["id"]

        with self.engine.begin() as conn:
            result = conn.execute(
                agent_versions.insert().values(
                    agent_id=agent_id,
                    version=next_v,
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
                    is_draft=1,
                )
            )
            pk = result.inserted_primary_key
            assert pk is not None
            new_vid = int(pk[0])
            _copy_version_files(conn, active_vid, new_vid)

        return self.get_version_by_id(new_vid) or {}

    def save_prompt_revision(
        self,
        agent_id: str,
        *,
        prompt_content: str,
        author: str,
        changelog: str = "",
        activate: bool = False,
    ) -> dict:
        """Create a new agent_version cloning active config but with new prompt_content.

        Every call yields a new row in ``agent_versions`` — the "draft slot
        is overwritten" behaviour from the legacy ``prompt_versions`` table
        does not apply here.

        Raises:
            ValueError: if no active version exists to clone from.
        """
        active = self.get_active_version(agent_id) or self.latest_version(agent_id)
        if active is None:
            raise ValueError(f"No version to clone for agent {agent_id}")

        next_v = self._next_version(agent_id)
        active_vid = active["id"]
        is_draft = 0 if activate else 1

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

        with self.engine.begin() as conn:
            result = conn.execute(
                agent_versions.insert().values(
                    agent_id=agent_id,
                    version=next_v,
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
                    is_draft=is_draft,
                )
            )
            pk = result.inserted_primary_key
            assert pk is not None
            new_vid = int(pk[0])
            _copy_version_files(conn, active_vid, new_vid)

            if activate:
                conn.execute(
                    active_agent_versions.delete().where(
                        active_agent_versions.c.agent_id == agent_id
                    )
                )
                conn.execute(
                    active_agent_versions.insert().values(
                        agent_id=agent_id,
                        version_id=new_vid,
                        activated_at=now_iso(),
                    )
                )

        return self.get_version_by_id(new_vid) or {}

    def save_config_revision(
        self,
        agent_id: str,
        *,
        config_patch: dict,
        author: str,
        changelog: str = "",
        activate: bool = True,
    ) -> dict:
        """Create a new agent_version with config_json merged from ``config_patch``.

        Deep-merges ``config_patch`` into the active version's ``config_json``
        (top-level keys are replaced wholesale; e.g. passing ``{"output": {...}}``
        replaces the entire ``output`` block). Carries prompt_content and files
        forward unchanged. Used by the push_agent_schemas tool to update the
        ``output`` contract block from the consumer.

        Raises:
            ValueError: if no active version exists to clone from.
        """
        active = self.get_active_version(agent_id) or self.latest_version(agent_id)
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
        new_hash = hashlib.sha256(new_config_str.encode("utf-8")).hexdigest()

        next_v = self._next_version(agent_id)
        active_vid = active["id"]
        is_draft = 0 if activate else 1

        with self.engine.begin() as conn:
            result = conn.execute(
                agent_versions.insert().values(
                    agent_id=agent_id,
                    version=next_v,
                    source_path=active.get("source_path") or "",
                    source_format=active.get("source_format") or "",
                    content_snapshot=active.get("content_snapshot") or "",
                    prompt_snapshot=active.get("prompt_snapshot") or "",
                    content_hash=new_hash,
                    author=author,
                    changelog=changelog or f"config edit from v{active['version']}",
                    is_legacy=0,
                    created_at=now_iso(),
                    config_json=new_config_str,
                    prompt_content=active.get("prompt_content"),
                    source=active.get("source", "ui"),
                    is_draft=is_draft,
                )
            )
            pk = result.inserted_primary_key
            assert pk is not None
            new_vid = int(pk[0])
            _copy_version_files(conn, active_vid, new_vid)

            if activate:
                conn.execute(
                    active_agent_versions.delete().where(
                        active_agent_versions.c.agent_id == agent_id
                    )
                )
                conn.execute(
                    active_agent_versions.insert().values(
                        agent_id=agent_id,
                        version_id=new_vid,
                        activated_at=now_iso(),
                    )
                )

        return self.get_version_by_id(new_vid) or {}


# ---------------------------------------------------------------------------
# Version-file CRUD + version create + activate
# ---------------------------------------------------------------------------


class _AgentVersionsFilesMixin(_AgentVersionsReadMixin):
    """Manage agent_version_files rows and low-level version inserts."""

    engine: Engine

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
        is_draft: bool = False,
    ) -> dict:
        prepared = _prepare_files(files) if files else []
        version = self._next_version(agent_id)
        with self.engine.begin() as conn:
            result = conn.execute(
                agent_versions.insert().values(
                    agent_id=agent_id,
                    version=version,
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
                    is_draft=int(is_draft),
                )
            )
            pk = result.inserted_primary_key
            assert pk is not None
            version_id = int(pk[0])
            if prepared:
                conn.execute(
                    agent_version_files.insert(),
                    [
                        {**row, "version_id": version_id, "created_at": now_iso()}
                        for row in prepared
                    ],
                )
        return self.get_version(agent_id, version)

    def insert_version_files(self, version_id: int, files: list[dict]) -> None:
        prepared = _prepare_files(files)
        if not prepared:
            return
        with self.engine.begin() as conn:
            conn.execute(
                agent_version_files.insert(),
                [
                    {**row, "version_id": version_id, "created_at": now_iso()}
                    for row in prepared
                ],
            )

    def replace_version_files(self, version_id: int, files: list[dict]) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                agent_version_files.delete().where(
                    agent_version_files.c.version_id == version_id
                )
            )
        if files:
            self.insert_version_files(version_id, files)

    def delete_version_files(self, version_id: int) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                agent_version_files.delete().where(
                    agent_version_files.c.version_id == version_id
                )
            )

    def delete_version_file(self, file_id: int) -> None:
        """Delete a single version file by ID."""
        with self.engine.begin() as conn:
            conn.execute(
                agent_version_files.delete().where(agent_version_files.c.id == file_id)
            )

    def replace_version_config(self, version_id: int, config_json: str) -> None:
        """Replace the config_json for a version in-place.

        Used by migrate-to-db-only to populate config_json on versions that
        predate DB-as-source-of-truth.
        """
        with self.engine.begin() as conn:
            conn.execute(
                agent_versions.update()
                .where(agent_versions.c.id == version_id)
                .values(config_json=config_json)
            )

    def activate_version(self, agent_id: str, version_id: int) -> None:
        """Pin *version_id* as the active version for *agent_id*."""
        with self.engine.begin() as conn:
            conn.execute(
                active_agent_versions.delete().where(
                    active_agent_versions.c.agent_id == agent_id
                )
            )
            conn.execute(
                active_agent_versions.insert().values(
                    agent_id=agent_id,
                    version_id=version_id,
                    activated_at=now_iso(),
                )
            )


# ---------------------------------------------------------------------------
# Agent-meta writes + comment/rating writes
# ---------------------------------------------------------------------------


class _AgentVersionsMetaMixin(_AgentVersionsReadMixin):
    """Mutations against agent_meta, agent_version_comments, agent_version_ratings."""

    engine: Engine

    # ------------------------------------------------------------------
    # Agent meta
    # ------------------------------------------------------------------

    def init_agent_meta(
        self,
        agent_id: str,
        sync_mode: str = "off",
        export_to_disk: bool = False,
        source_path: str | None = None,
        source_format: str | None = None,
    ) -> dict:
        existing = self.get_agent_meta(agent_id)
        now = now_iso()
        if existing is not None:
            return existing
        with self.engine.begin() as conn:
            conn.execute(
                agent_meta.insert().values(
                    agent_id=agent_id,
                    sync_mode=sync_mode,
                    export_to_disk=int(export_to_disk),
                    source_path=source_path,
                    source_format=source_format,
                    created_at=now,
                    updated_at=now,
                )
            )
        return self.get_agent_meta(agent_id) or {}

    def update_agent_meta(
        self,
        agent_id: str,
        sync_mode: str | None = None,
        export_to_disk: bool | None = None,
        source_path: str | None = None,
        source_format: str | None = None,
    ) -> dict | None:
        """Update agent_meta fields. Only supplied fields are changed."""
        existing = self.get_agent_meta(agent_id)
        if existing is None:
            return None
        now = now_iso()
        values: dict[str, object] = {"updated_at": now}
        if sync_mode is not None:
            values["sync_mode"] = sync_mode
        if export_to_disk is not None:
            values["export_to_disk"] = int(export_to_disk)
        if source_path is not None:
            values["source_path"] = source_path
        if source_format is not None:
            values["source_format"] = source_format
        with self.engine.begin() as conn:
            conn.execute(
                agent_meta.update()
                .where(agent_meta.c.agent_id == agent_id)
                .values(**values)
            )
        return self.get_agent_meta(agent_id)

    def soft_delete_agent(self, agent_id: str) -> dict | None:
        """Mark an agent as deleted by stamping ``agent_meta.deleted_at``.

        Idempotent: returns the current meta row whether or not the agent
        was already deleted. Returns ``None`` if the agent has no version
        history at all.
        """
        latest = self.latest_version(agent_id)
        if latest is None:
            return None
        now = now_iso()
        with self.engine.begin() as conn:
            existing = conn.execute(
                agent_meta.select().where(agent_meta.c.agent_id == agent_id)
            ).first()
            if existing:
                conn.execute(
                    agent_meta.update()
                    .where(agent_meta.c.agent_id == agent_id)
                    .values(deleted_at=now, updated_at=now)
                )
            else:
                conn.execute(
                    agent_meta.insert().values(
                        agent_id=agent_id,
                        sync_mode="off",
                        export_to_disk=0,
                        source_path=None,
                        source_format=None,
                        created_at=now,
                        updated_at=now,
                        deleted_at=now,
                    )
                )
            # Clear active pointer so the agent isn't runnable.
            conn.execute(
                active_agent_versions.delete().where(
                    active_agent_versions.c.agent_id == agent_id
                )
            )
        return self.get_agent_meta(agent_id)

    def restore_agent(self, agent_id: str) -> dict | None:
        """Clear ``deleted_at``. Active version pointer must be re-set
        separately if the caller wants the agent runnable again."""
        meta = self.get_agent_meta(agent_id)
        if meta is None:
            return None
        with self.engine.begin() as conn:
            conn.execute(
                agent_meta.update()
                .where(agent_meta.c.agent_id == agent_id)
                .values(deleted_at=None, updated_at=now_iso())
            )
        return self.get_agent_meta(agent_id)

    # ------------------------------------------------------------------
    # Comments / ratings
    # ------------------------------------------------------------------

    def add_comment(self, version_id: int, author: str, body: str) -> dict:
        with self.engine.begin() as conn:
            conn.execute(
                agent_version_comments.insert().values(
                    version_id=version_id,
                    author=author,
                    body=body,
                    created_at=now_iso(),
                )
            )
        return self.get_comment(version_id)

    def set_rating(self, version_id: int, rating: int, rater: str) -> dict:
        if not (1 <= rating <= 5):
            raise ValueError(f"rating must be 1-5, got {rating}")
        with self.engine.begin() as conn:
            conn.execute(
                agent_version_ratings.insert().values(
                    version_id=version_id,
                    rating=rating,
                    rater=rater,
                    rated_at=now_iso(),
                )
            )
        return self.get_rating(version_id) or {}


# ---------------------------------------------------------------------------
# Composite write mixin
# ---------------------------------------------------------------------------


class AgentWriteMixin(
    _AgentVersionsAgentMixin,
    _AgentVersionsRevisionsMixin,
    _AgentVersionsFilesMixin,
    _AgentVersionsMetaMixin,
):
    """All agent-version write operations."""
