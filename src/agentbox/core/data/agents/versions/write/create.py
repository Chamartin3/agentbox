"""Agent lifecycle: create agent, add version, publish, rollback."""

from __future__ import annotations

import hashlib
import json
import logging

from sqlalchemy.engine import Engine

from agentbox.core.data.agents.versions.models import _copy_version_files
from agentbox.core.data.agents.versions.read import _AgentVersionsReadMixin
from agentbox.core.data.agents.grants import AgentToolGrantsMixin
from agentbox.core.data.utils import now_iso
from agentbox.core.data.schema import (
    active_agent_versions,
    agent_meta,
    agent_versions,
)

logger = logging.getLogger(__name__)


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
    ) -> dict:
        """Append a new draft version on top of existing history.

        Primitive: no existence check, no soft-delete awareness. Inserts at
        ``max(version)+1`` and refreshes agent_meta (clearing ``deleted_at``).
        Callers decide when this is the right operation (e.g. the service
        layer uses it to re-create over a soft-deleted agent).
        """
        existing = self.latest_version(agent_id)
        next_version = (existing.get("version") or 0) + 1 if existing else 1

        content_hash = hashlib.sha256(
            json.dumps(config_json, sort_keys=True).encode("utf-8")
        ).hexdigest()
        config_str = json.dumps(config_json, sort_keys=True)

        with self.engine.begin() as conn:
            result = conn.execute(
                agent_versions.insert().values(
                    agent_id=agent_id,
                    version=next_version,
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
                )
            )
            pk = result.inserted_primary_key
            assert pk is not None
            version_id = int(pk[0])

            now = now_iso()
            existing_meta = conn.execute(
                agent_meta.select().where(agent_meta.c.agent_id == agent_id)
            ).first()
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
                        deleted_at=None,
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
        """Set the given version as active. Appends ``reason`` to changelog.

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
                .values(changelog=new_changelog)
            )

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
