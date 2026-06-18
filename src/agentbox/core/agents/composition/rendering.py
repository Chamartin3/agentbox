"""Render a resource version for prompt-embed callers.

Per-type semantics:

- ``document`` — the entire blob (text decoded).
- ``folder``  — a manifest listing of relative paths (NOT the bodies);
  folder embeds are summaries only.
- ``skill``   — the ``SKILL.md`` body only (the rest of the skill folder
  is delivered via workspace materialize, not prompt-embed).

Returned shape is a plain dict with ``text`` (for splicing into a prompt)
and ``metadata`` (for the per-run snapshot). The caller decides where
the text goes.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

SKILL_ENTRY = "SKILL.md"


def _blob_text(blob: dict) -> str:
    if blob.get("content_text"):
        return blob["content_text"]
    content = blob.get("content")
    if isinstance(content, (bytes, bytearray)):
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            return ""
    if isinstance(content, str):
        return content
    return ""


def render_document(blobs: Iterable[dict]) -> dict[str, Any]:
    blobs = list(blobs)
    body = _blob_text(blobs[0]) if blobs else ""
    return {"text": body, "metadata": {"role": "document"}}


def render_folder_manifest(blobs: Iterable[dict]) -> dict[str, Any]:
    blobs = list(blobs)
    paths = [b["relative_path"] for b in blobs if b.get("relative_path")]
    text = "\n".join(f"- {p}" for p in sorted(paths))
    return {
        "text": text,
        "metadata": {"role": "folder_manifest", "file_count": len(paths)},
    }


def render_skill_primer(blobs: Iterable[dict]) -> dict[str, Any]:
    blobs = list(blobs)
    entry = next((b for b in blobs if b.get("relative_path") == SKILL_ENTRY), None)
    if entry is None:
        return {"text": "", "metadata": {"role": "skill_primer", "missing_entry": True}}
    return {
        "text": _blob_text(entry),
        "metadata": {
            "role": "skill_primer",
            "entry_path": SKILL_ENTRY,
            "file_count": len(blobs),
        },
    }


def render_schema(blobs: Iterable[dict]) -> dict[str, Any]:
    blobs = list(blobs)
    body = _blob_text(blobs[0]) if blobs else ""
    return {"text": body, "metadata": {"role": "schema"}}


def render_script(blobs: Iterable[dict]) -> dict[str, Any]:
    blobs = list(blobs)
    body = _blob_text(blobs[0]) if blobs else ""
    return {"text": body, "metadata": {"role": "script"}}


def render_for_type(type: str, blobs: Iterable[dict]) -> dict[str, Any]:
    if type == "document":
        return render_document(blobs)
    if type == "folder":
        return render_folder_manifest(blobs)
    if type == "skill":
        return render_skill_primer(blobs)
    if type == "schema":
        return render_schema(blobs)
    if type == "script":
        return render_script(blobs)
    raise ValueError(f"Unknown resource type for rendering: {type!r}")
