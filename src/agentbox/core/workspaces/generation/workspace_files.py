"""Copy declared workspace files into a run/workspace dir.

Engine-agnostic: ``WorkenvConfig`` declares host paths to project into the
run cwd; this materializes them. Was ``engine_config/_common.py``.
"""

from __future__ import annotations

import shutil
from pathlib import Path


def materialize_workspace_files(
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
