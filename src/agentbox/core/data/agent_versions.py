"""Agent-versions mixin: create, list, get, diff, comment, rate.

Composed into ``SessionStore``. Reads ``self.engine`` and operates on
``agent_versions`` + ``agent_version_comments`` + ``agent_version_ratings``.
"""

from __future__ import annotations

import hashlib
import json
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
        sync_mode: str = "watch",
        export_to_disk: bool = True,
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

    def get_version(self, agent_id: str, version: int) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                agent_versions.select().where(
                    agent_versions.c.agent_id == agent_id,
                    agent_versions.c.version == version,
                )
            ).first()
            return self._row_dict(row) if row else None

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
        snap = latest.get("content_snapshot")
        if not snap:
            return None
        try:
            data = json.loads(snap)
        except json.JSONDecodeError:
            logger.warning(
                "agent_versions: snapshot for %r v%s is not valid JSON",
                agent_id,
                latest.get("version"),
            )
            return None
        try:
            return AgentDef.model_validate(data)
        except Exception as exc:
            logger.warning(
                "agent_versions: snapshot for %r v%s failed validation: %s",
                agent_id,
                latest.get("version"),
                exc,
            )
            return None

    def list_agents_with_latest(self) -> list[dict]:
        """Return one row per agent_id — the latest version's snapshot.

        DB-as-source-of-truth read path for the agent list. Avoids hitting
        the filesystem loader so the API surfaces exactly what was imported
        into ``agent_versions`` (including DB-only agents with no on-disk
        bundle).
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
            rows = conn.execute(
                agent_versions.select()
                .join(
                    inner,
                    (agent_versions.c.agent_id == inner.c.agent_id)
                    & (agent_versions.c.version == inner.c.max_version),
                )
                .order_by(agent_versions.c.created_at.desc())
            )
            return [self._row_dict(r) for r in rows]

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
