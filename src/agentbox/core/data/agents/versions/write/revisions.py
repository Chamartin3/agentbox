"""Revisions: branch drafts, prompt edits, config edits."""

from __future__ import annotations

import hashlib
import json

from sqlalchemy.engine import Engine

from agentbox.core.data.agents.versions.models import _copy_version_files
from agentbox.core.data.agents.versions.read import _AgentVersionsReadMixin
from agentbox.core.data.utils import now_iso
from agentbox.core.data.schema import (
    active_agent_versions,
    agent_versions,
)


class _AgentVersionsRevisionsMixin(_AgentVersionsReadMixin):
    """Clone-from-active version writes (drafts, prompt edits, config edits)."""

    engine: Engine

    def branch_draft(self, agent_id: str, *, author: str) -> dict:
        """Clone the active version into a new (inactive) version.

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
