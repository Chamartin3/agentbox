"""JSONL transcript reader. Transcripts are stored on the filesystem, not in the DB."""

from __future__ import annotations

import json
from pathlib import Path


def resolve_transcript_path(
    stored_path: str | Path, data_dir: Path | None = None
) -> Path:
    """Resolve a stored transcript path to one that actually exists.

    The DB stores transcript paths as absolute (e.g. ``/data/transcripts/<hex>.jsonl``)
    — that's the path inside the executor container. Callers in other
    containers (the MCP server, host-side tooling) may have ``/data``
    mapped to a different mount or not at all. When the stored path
    doesn't exist, fall back to ``<data_dir>/transcripts/<basename>``.
    """
    p = Path(stored_path)
    if p.exists():
        return p
    if data_dir is not None:
        candidate = Path(data_dir) / "transcripts" / p.name
        if candidate.exists():
            return candidate
    return p


def read_transcript(path: Path, data_dir: Path | None = None) -> list[dict]:
    resolved = resolve_transcript_path(path, data_dir)
    if not resolved.exists():
        return []
    out: list[dict] = []
    for line in resolved.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
