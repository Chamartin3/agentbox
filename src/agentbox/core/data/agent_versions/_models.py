"""Shared constants and helpers for the agent_versions sub-package."""

from __future__ import annotations

import hashlib

from agentbox.core.data.records import now_iso
from agentbox.core.data.schema import agent_version_files

_VALID_FILE_KINDS = {
    "system",
    "user_template",
    "reference",
    "output_schema",
    "input_schema",
    "other",
}


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


def _copy_version_files(conn, src_version_id: int, dst_version_id: int) -> None:
    """Copy all ``agent_version_files`` rows from ``src`` to ``dst``."""
    files = conn.execute(
        agent_version_files.select().where(
            agent_version_files.c.version_id == src_version_id
        )
    ).fetchall()
    if not files:
        return
    conn.execute(
        agent_version_files.insert(),
        [
            {
                "version_id": dst_version_id,
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
