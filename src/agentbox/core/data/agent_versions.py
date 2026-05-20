"""Agent-versions mixin: create, list, get, diff, comment, rate.

Composed into ``SessionStore``. Reads ``self.engine`` and operates on
``agent_versions`` + ``agent_version_comments`` + ``agent_version_ratings``.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.engine import Engine

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

_VALID_FILE_KINDS = {
    "system",
    "user_template",
    "reference",
    "output_schema",
    "input_schema",
    "other",
}


class AgentVersionsMixin:
    """Versioned agent persistence. Requires ``self.engine: Engine``."""

    engine: Engine

    # ------------------------------------------------------------------
    # Agent lifecycle
    # ------------------------------------------------------------------

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

        Args:
            agent_id: Unique agent identifier.
            config_json: Agent configuration dict.
            prompt_content: Optional system prompt text.
            author: Author name.
            changelog: Version changelog.
            source: Source type ("ui", "manifest", or "import").
            source_path: Optional path to source file.
            source_format: Optional source format.
            sync_mode: File sync mode ("off", "watch", "manual").
            export_to_disk: Whether to export to disk.

        Returns:
            AgentVersionRecord (dict) for the new v1 draft.

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
            # Insert v1 draft
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
            version_id = int(result.inserted_primary_key[0])

            # Insert or update agent_meta
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

    def publish_version(
        self, agent_id: str, version: int, reason: str
    ) -> dict:
        """Flip is_draft flag and set as active version.

        Args:
            agent_id: Agent identifier.
            version: Version number to publish.
            reason: Reason for publishing (≥ 3 chars).

        Returns:
            Updated AgentVersionRecord (dict).

        Raises:
            ValueError: if reason is empty or < 3 chars, or version not found.
        """
        if not reason or len(reason) < 3:
            raise ValueError("reason must be at least 3 characters")

        # Fetch the version
        row = self._get_version_row(agent_id, version)
        if row is None:
            raise ValueError(f"version {version} not found for agent {agent_id}")

        version_id = row["id"]
        old_changelog = row.get("changelog") or ""
        new_changelog = (
            f"{old_changelog}\n\npublish: {reason}"
            if old_changelog
            else reason
        )

        with self.engine.begin() as conn:
            # Update version: flip is_draft and append changelog
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

            # Upsert active pointer
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

    def branch_draft(self, agent_id: str, *, author: str) -> dict:
        """Clone the active version into a new draft.

        Args:
            agent_id: Agent identifier.
            author: Author name for the new draft.

        Returns:
            New draft AgentVersionRecord (dict).

        Raises:
            ValueError: if no active version exists.
        """
        active = self.get_active_version(agent_id)
        if active is None:
            raise ValueError(f"No active version for agent {agent_id}")

        next_v = self._next_version(agent_id)
        active_vid = active["id"]

        with self.engine.begin() as conn:
            # Insert new draft version
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
            new_vid = int(result.inserted_primary_key[0])

            # Copy files
            files = conn.execute(
                agent_version_files.select().where(
                    agent_version_files.c.version_id == active_vid
                )
            ).fetchall()
            if files:
                conn.execute(
                    agent_version_files.insert(),
                    [
                        {
                            "version_id": new_vid,
                            "relative_path": f._mapping["relative_path"],
                            "kind": f._mapping["kind"],
                            "content": f._mapping["content"],
                            "sha256": f._mapping["sha256"],
                            "source_uri": f._mapping.get("source_uri"),
                            "position": f._mapping.get("position", 0),
                            "created_at": now_iso(),
                        }
                        for f in files
                    ],
                )

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

        Args:
            agent_id: Agent identifier.
            prompt_content: New prompt body.
            author: Author label.
            changelog: Short message (stored on row).
            activate: If True, also flip ``is_draft=False`` and set as active.

        Returns:
            New AgentVersionRecord (dict).

        Raises:
            ValueError: if no active version exists to clone from.
        """
        active = self.get_active_version(agent_id) or self.latest_version(agent_id)
        if active is None:
            raise ValueError(f"No version to clone for agent {agent_id}")

        next_v = self._next_version(agent_id)
        active_vid = active["id"]
        is_draft = 0 if activate else 1

        # Keep config_json["prompt"] in sync with the new prompt_content.
        # AgentDef.from_db_row rehydrates `agent.prompt` from config_json,
        # so a stale value here makes the runtime + preview render the
        # old body even though prompt_content is current.
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
            new_vid = int(result.inserted_primary_key[0])

            files = conn.execute(
                agent_version_files.select().where(
                    agent_version_files.c.version_id == active_vid
                )
            ).fetchall()
            if files:
                conn.execute(
                    agent_version_files.insert(),
                    [
                        {
                            "version_id": new_vid,
                            "relative_path": f._mapping["relative_path"],
                            "kind": f._mapping["kind"],
                            "content": f._mapping["content"],
                            "sha256": f._mapping["sha256"],
                            "source_uri": f._mapping.get("source_uri"),
                            "position": f._mapping.get("position", 0),
                            "created_at": now_iso(),
                        }
                        for f in files
                    ],
                )

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

        # Carry validation bindings forward so a prompt edit does not silently
        # drop the agent's contracts. Mirrors ``upsert_version`` below.
        try:
            self.clone_validation_bindings(  # type: ignore[attr-defined]
                from_version_id=active_vid, to_version_id=new_vid
            )
        except Exception:  # noqa: BLE001 — best-effort, never block prompt edit
            pass

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

        Args:
            agent_id: Agent identifier.
            config_patch: Top-level keys to merge into config_json.
            author: Author label.
            changelog: Short message stored on the new row.
            activate: If True (default), the new version is activated.

        Returns:
            New AgentVersionRecord (dict).

        Raises:
            ValueError: if no active version exists to clone from.
        """
        active = self.get_active_version(agent_id) or self.latest_version(agent_id)
        if active is None:
            raise ValueError(f"No version to clone for agent {agent_id}")

        raw = active.get("config_json")
        try:
            current_cfg = json.loads(raw) if isinstance(raw, str) and raw else (raw or {})
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
            new_vid = int(result.inserted_primary_key[0])

            files = conn.execute(
                agent_version_files.select().where(
                    agent_version_files.c.version_id == active_vid
                )
            ).fetchall()
            if files:
                conn.execute(
                    agent_version_files.insert(),
                    [
                        {
                            "version_id": new_vid,
                            "relative_path": f._mapping["relative_path"],
                            "kind": f._mapping["kind"],
                            "content": f._mapping["content"],
                            "sha256": f._mapping["sha256"],
                            "source_uri": f._mapping.get("source_uri"),
                            "position": f._mapping.get("position", 0),
                            "created_at": now_iso(),
                        }
                        for f in files
                    ],
                )

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

    def rollback_to(
        self, agent_id: str, target_version: int, reason: str, *, author: str
    ) -> dict:
        """Create a new version rolling back to target_version's config.

        Args:
            agent_id: Agent identifier.
            target_version: Version number to roll back to.
            reason: Reason for rollback (≥ 3 chars).
            author: Author name for the new version.

        Returns:
            New (non-draft) AgentVersionRecord and sets as active.

        Raises:
            ValueError: if reason < 3 chars or target_version not found.
        """
        if not reason or len(reason) < 3:
            raise ValueError("reason must be at least 3 characters")

        # Fetch target version
        target_row = self._get_version_row(agent_id, target_version)
        if target_row is None:
            raise ValueError(
                f"target_version {target_version} not found for agent {agent_id}"
            )

        next_v = self._next_version(agent_id)
        target_vid = target_row["id"]

        with self.engine.begin() as conn:
            # Create new version with target's config
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
            new_vid = int(result.inserted_primary_key[0])

            # Copy files from target
            files = conn.execute(
                agent_version_files.select().where(
                    agent_version_files.c.version_id == target_vid
                )
            ).fetchall()
            if files:
                conn.execute(
                    agent_version_files.insert(),
                    [
                        {
                            "version_id": new_vid,
                            "relative_path": f._mapping["relative_path"],
                            "kind": f._mapping["kind"],
                            "content": f._mapping["content"],
                            "sha256": f._mapping["sha256"],
                            "source_uri": f._mapping.get("source_uri"),
                            "position": f._mapping.get("position", 0),
                            "created_at": now_iso(),
                        }
                        for f in files
                    ],
                )

            # Set as active
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

    # ------------------------------------------------------------------
    # Versions
    # ------------------------------------------------------------------

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
        # Resolve the prior active version *before* the new insert, so we
        # know whose validation bindings to carry forward.
        prior_active = self.get_active_version(agent_id)  # type: ignore[attr-defined]
        prior_version_id = (
            int(prior_active["id"])
            if prior_active and prior_active.get("id") is not None
            else None
        )
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
            version_id = int(result.inserted_primary_key[0])
            if prepared:
                conn.execute(
                    agent_version_files.insert(),
                    [
                        {**row, "version_id": version_id, "created_at": now_iso()}
                        for row in prepared
                    ],
                )
        # Carry validation bindings forward from the previous active row
        # so contracts follow the agent across edits unless explicitly
        # changed via the validation endpoint.
        if prior_version_id is not None:
            try:
                self.clone_validation_bindings(  # type: ignore[attr-defined]
                    from_version_id=prior_version_id, to_version_id=version_id
                )
            except Exception:  # noqa: BLE001 — best-effort, never block version create
                pass
        return self.get_version(agent_id, version)

    # ------------------------------------------------------------------
    # Bundle files
    # ------------------------------------------------------------------

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

    def list_version_files(self, version_id: int) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                agent_version_files.select()
                .where(agent_version_files.c.version_id == version_id)
                .order_by(
                    agent_version_files.c.position, agent_version_files.c.id
                )
            )
            return [dict(r._mapping) for r in rows]

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
                agent_version_files.delete().where(
                    agent_version_files.c.id == file_id
                )
            )

    def latest_version(self, agent_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                agent_versions.select()
                .where(agent_versions.c.agent_id == agent_id)
                .order_by(agent_versions.c.version.desc())
                .limit(1)
            ).first()
            return self._row_dict(row) if row else None

    def get_active_version(self, agent_id: str) -> dict | None:
        """Return the active version pointed at by ``active_agent_versions``.

        Returns ``None`` when no pointer is set — callers either fall
        back to the disk bundle or wait for ``startup_sweep`` to heal
        the missing pointer. Promotion is explicit via
        ``activate_version`` so that the UI/CLI never silently picks a
        version the operator didn't endorse.
        """
        with self.engine.connect() as conn:
            pointer = conn.execute(
                active_agent_versions.select().where(
                    active_agent_versions.c.agent_id == agent_id
                )
            ).first()
            if pointer is None:
                return None
            row = conn.execute(
                agent_versions.select().where(
                    agent_versions.c.id == pointer._mapping["version_id"]
                )
            ).first()
            return self._row_dict(row) if row else None

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

    # ------------------------------------------------------------------
    # Agent meta (non-versioned per-agent settings)
    # ------------------------------------------------------------------

    def get_agent_meta(self, agent_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                agent_meta.select().where(agent_meta.c.agent_id == agent_id)
            ).first()
            return dict(row._mapping) if row else None

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
        """Update agent_meta fields. Only supplied fields are changed.

        Args:
            agent_id: Agent identifier.
            sync_mode: New sync_mode value (None = no change).
            export_to_disk: New export_to_disk value (None = no change).
            source_path: New source_path value (None = no change).
            source_format: New source_format value (None = no change).

        Returns:
            Updated agent_meta dict, or None if agent_meta doesn't exist.
        """
        existing = self.get_agent_meta(agent_id)
        if existing is None:
            return None
        now = now_iso()
        values = {"updated_at": now}
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

    def get_version_by_id(self, version_id: int) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                agent_versions.select().where(agent_versions.c.id == version_id)
            ).first()
            return self._row_dict(row) if row else None

    def get_version(self, agent_id: str, version: int) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                agent_versions.select().where(
                    agent_versions.c.agent_id == agent_id,
                    agent_versions.c.version == version,
                )
            ).first()
            return self._row_dict(row) if row else None

    def replace_version_config(self, version_id: int, config_json: str) -> None:
        """Replace the config_json for a version in-place.

        Used by migrate-to-db-only to populate config_json on versions that
        predate DB-as-source-of-truth.

        Args:
            version_id: Version ID to update.
            config_json: New config_json content (JSON string).
        """
        with self.engine.begin() as conn:
            conn.execute(
                agent_versions.update()
                .where(agent_versions.c.id == version_id)
                .values(config_json=config_json)
            )

    def get_agent_def(self, agent_id: str):  # -> AgentDef | None
        """Reconstruct an ``AgentDef`` from the latest version's snapshot.

        Returns ``None`` when the agent has never been versioned. Callers
        should prefer this over ``DefinitionLoader.get()`` so runtime
        behavior is driven by the DB, not the filesystem.
        """
        import logging

        from agentbox.core.data.manifest import AgentDef

        logger = logging.getLogger(__name__)

        latest = self.latest_version(agent_id)
        if latest is None:
            return None
        if self.is_agent_deleted(agent_id):
            return None
        try:
            return AgentDef.from_db_row(latest)
        except ValueError:
            # No config_json or content_snapshot — incomplete row.
            return None
        except Exception as exc:
            logger.warning(
                "agent_versions: row for %r v%s failed validation: %s",
                agent_id,
                latest.get("version"),
                exc,
            )
            return None

    def list_agents_with_latest(self, include_deleted: bool = False) -> list[dict]:
        """Return one row per agent_id — the latest version's snapshot.

        DB-as-source-of-truth read path for the agent list. Avoids hitting
        the filesystem loader so the API surfaces exactly what was imported
        into ``agent_versions`` (including DB-only agents with no on-disk
        bundle).

        Soft-deleted agents (``agent_meta.deleted_at IS NOT NULL``) are
        excluded by default.
        """
        with self.engine.connect() as conn:
            inner = (
                select(
                    agent_versions.c.agent_id,
                    func.max(agent_versions.c.version).label("max_version"),
                )
                .group_by(agent_versions.c.agent_id)
                .subquery()
            )
            q = (
                agent_versions.select()
                .join(
                    inner,
                    (agent_versions.c.agent_id == inner.c.agent_id)
                    & (agent_versions.c.version == inner.c.max_version),
                )
                .order_by(agent_versions.c.created_at.desc())
            )
            rows = list(conn.execute(q))
            if include_deleted:
                return [self._row_dict(r) for r in rows]
            deleted_ids = {
                r._mapping["agent_id"]
                for r in conn.execute(
                    agent_meta.select().where(
                        agent_meta.c.deleted_at.isnot(None)
                    )
                )
            }
            return [
                self._row_dict(r)
                for r in rows
                if self._row_dict(r).get("agent_id") not in deleted_ids
            ]

    def is_agent_deleted(self, agent_id: str) -> bool:
        meta = self.get_agent_meta(agent_id)
        return bool(meta and meta.get("deleted_at"))

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

    def list_versions(self, agent_id: str) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                agent_versions.select()
                .where(agent_versions.c.agent_id == agent_id)
                .order_by(agent_versions.c.version.desc())
            )
            return [self._row_dict(r) for r in rows]

    def diff_versions(self, agent_id: str, a: int, b: int) -> dict[str, Any]:
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

    # ------------------------------------------------------------------
    # Comments
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

    def get_comment(self, version_id: int) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                agent_version_comments.select().where(
                    agent_version_comments.c.version_id == version_id
                )
            ).first()
            return dict(row._mapping) if row else None

    def list_comments(self, version_id: int) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                agent_version_comments.select()
                .where(agent_version_comments.c.version_id == version_id)
                .order_by(agent_version_comments.c.created_at)
            )
            return [dict(r._mapping) for r in rows]

    # ------------------------------------------------------------------
    # Ratings
    # ------------------------------------------------------------------

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

    def get_rating(self, version_id: int) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                agent_version_ratings.select().where(
                    agent_version_ratings.c.version_id == version_id
                )
            ).first()
            return dict(row._mapping) if row else None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _next_version(self, agent_id: str) -> int:
        with self.engine.connect() as conn:
            row = conn.execute(
                select(func.coalesce(func.max(agent_versions.c.version), 0)).where(
                    agent_versions.c.agent_id == agent_id
                )
            ).first()
            return int(row[0]) + 1 if row else 1

    def _get_version_row(self, agent_id: str, version: int) -> dict | None:
        """Low-level: fetch raw version row as dict."""
        with self.engine.connect() as conn:
            row = conn.execute(
                agent_versions.select().where(
                    agent_versions.c.agent_id == agent_id,
                    agent_versions.c.version == version,
                )
            ).first()
            return self._row_dict(row) if row else None

    @staticmethod
    def _row_dict(row: Any) -> dict:
        d = dict(row._mapping)
        d["is_legacy"] = bool(d.get("is_legacy", False))
        return d


def _prepare_files(files: list[dict]) -> list[dict]:
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
        sha256 = f.get("sha256") or hashlib.sha256(content.encode("utf-8")).hexdigest()
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
    lines_a = a.splitlines(keepends=True)
    lines_b = b.splitlines(keepends=True)

    try:
        import difflib
    except ImportError:
        return f"<{len(lines_a)} lines → {len(lines_b)} lines>"

    return "".join(difflib.unified_diff(lines_a, lines_b, lineterm=""))


def _json_diff(a: str, b: str) -> dict:
    try:
        obj_a = json.loads(a) if a else {}
        obj_b = json.loads(b) if b else {}
    except json.JSONDecodeError:
        return {"from": a, "to": b, "note": "invalid JSON"}
    added = {k: obj_b[k] for k in obj_b if k not in obj_a}
    removed = {k: obj_a[k] for k in obj_a if k not in obj_b}
    changed = {
        k: {"from": obj_a[k], "to": obj_b[k]}
        for k in obj_a
        if k in obj_b and obj_a[k] != obj_b[k]
    }
    return {"added": added, "removed": removed, "changed": changed}
