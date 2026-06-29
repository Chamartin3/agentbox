"""Shared utility functions — non-domain helpers used across packages.

``now_iso`` (extracted from ``core.db.utils``) and ``hash_blobs``
(extracted from ``core.db.resources._rows``) live here so they can be
imported from ``core.data`` without pulling in persistence code.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import UTC, datetime


def now_iso() -> str:
    """Return current UTC timestamp as an ISO 8601 string (second precision)."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def hash_blobs(blobs: Iterable[tuple[str, bytes]]) -> str:
    """Deterministic hash over a (relative_path, content) sequence."""
    h = hashlib.sha256()
    for rel_path, content in sorted(blobs, key=lambda b: b[0]):
        h.update(rel_path.encode("utf-8"))
        h.update(b"\x00")
        h.update(hashlib.sha256(content).digest())
        h.update(b"\x00")
    return h.hexdigest()
