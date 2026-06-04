"""Resource blob cache for symlink materialization (Plan 08 Phase 2).

``ensure_cached(version_id, blobs, cache_root)`` writes blobs to
``<cache_root>/<version_id>/`` exactly once (idempotent). Uses an
atomic write via a temp dir + rename so concurrent runs hitting the
same version never see a partial cache entry.

The cache is content-addressed by version_id. Callers that want a
fresh copy must invalidate by removing the directory.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path


def ensure_cached(version_id: str, blobs: list[dict], cache_root: Path) -> Path:
    """Return ``<cache_root>/<version_id>`` with all blobs written inside.

    Idempotent: if the directory already exists it is returned immediately.
    Atomic: blobs are written to a temp dir first; the temp dir is renamed
    into place so a concurrent caller that beats us to the rename will still
    find a complete directory.

    Each blob dict must have:
        path (str)     — relative path within the cache entry
        content (bytes | str) — file content

    Returns the cache entry directory path.
    """
    cache_root = Path(cache_root)
    cache_root.mkdir(parents=True, exist_ok=True)

    dest = cache_root / version_id
    if dest.exists():
        return dest

    # Write to a uniquely-named tmp dir in the same parent so the rename
    # is on the same filesystem (required for atomic os.rename on Linux).
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"_tmp_{version_id}_", dir=cache_root))
    try:
        for blob in blobs:
            rel = blob.get("path", "")
            content = blob.get("content", b"")
            target = tmp_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, str):
                target.write_text(content, encoding="utf-8")
            else:
                target.write_bytes(content)

        try:
            os.rename(tmp_dir, dest)
        except OSError:
            # Another process won the race — our tmp becomes orphaned; clean up.
            shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    return dest


def prune_cache(cache_root: Path, *, older_than_days: float = 30.0) -> int:
    """Remove cache entries not accessed within ``older_than_days`` days.

    Returns the number of entries deleted.
    """
    if not cache_root.exists():
        return 0

    cutoff = time.time() - older_than_days * 86400
    removed = 0
    for entry in cache_root.iterdir():
        if not entry.is_dir():
            continue
        try:
            stat = entry.stat()
            atime = max(stat.st_atime, stat.st_mtime)
            if atime < cutoff:
                shutil.rmtree(entry, ignore_errors=True)
                removed += 1
        except OSError:
            continue
    return removed
