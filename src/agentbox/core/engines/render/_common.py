"""Shared utilities for render builders — no domain imports."""

from __future__ import annotations

import json
import shutil
from collections.abc import Sequence
from pathlib import Path

from .constants import (
    CLAUDE_MCP_PREFIX,
    CLAUDE_TO_OPENCODE_TOOLS,
    OPENCODE_MCP_PREFIX,
    READ_PREFIXES,
)


def _dump_json(path: Path, data: object) -> Path:
    """Write ``data`` to ``path`` as pretty-printed JSON. Returns ``path``."""
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return path


def _is_read_tool_claude(tool: str, prefix: str = CLAUDE_MCP_PREFIX) -> bool:
    if not tool.startswith(prefix):
        return False
    suffix = tool[len(prefix):]
    if any(suffix.startswith(rp) for rp in READ_PREFIXES):
        return True
    parts = suffix.split("_", 1)
    return len(parts) == 2 and any(parts[1].startswith(rp) for rp in READ_PREFIXES)


def _claude_tool_to_opencode(tool: str) -> str:
    if tool in CLAUDE_TO_OPENCODE_TOOLS:
        return CLAUDE_TO_OPENCODE_TOOLS[tool]
    if tool.startswith(CLAUDE_MCP_PREFIX):
        suffix = tool[len(CLAUDE_MCP_PREFIX):]
        return f"{OPENCODE_MCP_PREFIX}{suffix}"
    return tool


def _is_read_tool_opencode(tool: str) -> bool:
    if not tool.startswith(OPENCODE_MCP_PREFIX):
        return False
    suffix = tool[len(OPENCODE_MCP_PREFIX):]
    parts = suffix.split("_", 1)
    return len(parts) == 2 and any(parts[1].startswith(rp) for rp in READ_PREFIXES)


def _materialize_workspace_files(
    workspace_path: Path,
    files: list[dict],
    project_root: Path,
) -> int:
    """Copy declared host paths into the workspace cwd.

    Each entry is ``{src, dst}`` where ``src`` is resolved relative to
    ``project_root`` and ``dst`` is relative to ``workspace_path``.
    Existing destinations are removed first so the copy stays in sync
    with the source. Symlinks pointing outside the workspace are not
    supported (docker bind mounts cannot follow them).
    """
    count = 0
    for entry in files:
        if not isinstance(entry, dict):
            continue
        src_rel = entry.get("src")
        dst_rel = entry.get("dst")
        if not isinstance(src_rel, str) or not isinstance(dst_rel, str):
            continue
        src = (project_root / src_rel).resolve()
        if not src.exists():
            raise FileNotFoundError(f"workspace files: source does not exist: {src}")
        dst = workspace_path / dst_rel
        if dst.is_symlink() or dst.exists():
            if dst.is_dir() and not dst.is_symlink():
                shutil.rmtree(dst)
            else:
                dst.unlink()
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        count += 1
    return count
