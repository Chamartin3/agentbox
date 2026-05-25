"""Version diff helpers for AgentVersionsMixin."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.engine import Engine


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


class _AgentVersionsDiffMixin:
    """Diff queries over agent_versions rows."""

    engine: Engine

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
