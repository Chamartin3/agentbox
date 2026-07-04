"""Shared workdir path-safety guard for every DB→disk projection writer.

All three writers under ``core/workspaces`` (``generator.render``,
``materialize`` bindings, ``workspace_files`` host copies) resolve a
relative path under the workdir and write to it. This is the one thing
they genuinely share: the guarantee that the resolved destination stays
inside the workdir. Keep it in one place so the guard can't drift or go
missing on one writer.
"""

from __future__ import annotations

from pathlib import Path


def safe_dest(root: Path, rel: str) -> Path:
    """Resolve ``rel`` under ``root``, rejecting path-traversal attempts."""
    if rel.startswith("/"):
        raise ValueError(f"target_path {rel!r} must be relative")
    parts = [p for p in rel.split("/") if p]
    if any(p == ".." for p in parts):
        raise ValueError(f"target_path {rel!r} must not contain '..'")
    out = (root / Path(*parts)).resolve()
    if not str(out).startswith(str(root.resolve())):
        raise ValueError(f"target_path {rel!r} escapes workdir")
    return out
