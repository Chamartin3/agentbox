"""Write a resource version's blobs into a target directory.

Used by Plan 03 (workspace file-materialize bindings) to lay resources
into the run workdir. Kept in core/resources so the same materializer
can be reused by tests and CLI.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path


def materialize_blobs(
    blobs: Iterable[dict],
    target_root: Path,
    *,
    overwrite: bool = True,
) -> list[Path]:
    """Write ``iter_repo_blobs(version_id)`` output into ``target_root``.

    Returns the list of paths actually written. Directories are created
    as needed. ``relative_path == ""`` means "write the single document
    blob to ``target_root`` itself" — for a folder/skill use the
    sub-paths as-is.
    """
    target_root = Path(target_root)
    target_root.parent.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    blobs = list(blobs)
    is_single_doc = len(blobs) == 1 and blobs[0]["relative_path"] == ""
    if is_single_doc:
        # Document — target_root is the file path itself.
        if target_root.exists() and not overwrite:
            return []
        target_root.parent.mkdir(parents=True, exist_ok=True)
        target_root.write_bytes(blobs[0]["content"])
        written.append(target_root)
        return written

    # Folder / skill — target_root is a directory.
    target_root.mkdir(parents=True, exist_ok=True)
    for blob in blobs:
        rel = blob["relative_path"]
        if not rel:
            # Defensive: a folder version should never have an empty
            # rel-path entry — skip rather than smash the directory.
            continue
        dest = target_root / rel
        if dest.exists() and not overwrite:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(blob["content"])
        written.append(dest)
    return written
