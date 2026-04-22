"""Agent-versions mixin: create, list, get, diff, comment, rate.

Composed into ``SessionStore``. Reads ``self.engine`` and operates on
``agent_versions`` + ``agent_version_comments`` + ``agent_version_ratings``.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from agentbox.core.data.records import now_iso
from agentbox.core.data.schema import (
    agent_version_comments,
    agent_version_ratings,
    agent_versions,
)


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
    ) -> dict:
        version = self._next_version(agent_id)
        with self.engine.begin() as conn:
            conn.execute(
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
                )
            )
        return self.get_version(agent_id, version)

    def latest_version(self, agent_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                agent_versions.select()
                .where(agent_versions.c.agent_id == agent_id)
                .order_by(agent_versions.c.version.desc())
                .limit(1)
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

    def list_versions(self, agent_id: str) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                agent_versions.select()
                .where(agent_versions.c.agent_id == agent_id)
                .order_by(agent_versions.c.version.desc())
            )
            return [self._row_dict(r) for r in rows]

    def diff_versions(
        self, agent_id: str, a: int, b: int
    ) -> dict[str, Any]:
        va = self.get_version(agent_id, a)
        vb = self.get_version(agent_id, b)
        if va is None or vb is None:
            raise ValueError(f"version not found: {a if va is None else b}")
        return {
            "from_version": a,
            "to_version": b,
            "prompt_diff": _text_diff(
                va["prompt_snapshot"], vb["prompt_snapshot"]
            ),
            "content_diff": _json_diff(
                va["content_snapshot"], vb["content_snapshot"]
            ),
        }

    # ------------------------------------------------------------------
    # Comments
    # ------------------------------------------------------------------

    def add_comment(
        self, version_id: int, author: str, body: str
    ) -> dict:
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

    def set_rating(
        self, version_id: int, rating: int, rater: str
    ) -> dict:
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


def _text_diff(a: str, b: str) -> str:
    if a == b:
        return ""
    lines_a = a.splitlines(keepends=True)
    lines_b = b.splitlines(keepends=True)

    try:
        import difflib
    except ImportError:
        return f"<{len(lines_a)} lines → {len(lines_b)} lines>"

    return "".join(
        difflib.unified_diff(lines_a, lines_b, lineterm="")
    )


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
