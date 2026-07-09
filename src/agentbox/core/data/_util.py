"""Shared utility functions — non-domain helpers used across packages.

``now_iso`` (extracted from ``core.db.utils``), ``hash_blobs``
(extracted from ``core.db.resources._rows``), and ``extract_json``
(extracted from ``core.agents.validation.errors``) live here so they can be
imported from ``core.data`` without pulling in persistence or backend code.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from datetime import UTC, datetime


_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*\n(.*?)\n```", re.DOTALL)


def extract_json(text: str) -> str:
    """Pull a JSON payload out of prose-wrapped model output.

    Models often wrap JSON in ``` fences plus surrounding prose despite
    being told not to. Validation should still engage on the JSON they
    produced, so we extract the first fenced block when present, then
    fall back to the first ``{...}`` / ``[...]`` slice, then return the
    raw text unchanged for ``json.loads`` to fail on naturally.
    """
    if not text:
        return text
    m = _FENCED_JSON_RE.search(text)
    if m:
        return m.group(1).strip()
    s = text.strip()
    if s.startswith(("{", "[")):
        return s
    for opener, closer in (("{", "}"), ("[", "]")):
        i = s.find(opener)
        j = s.rfind(closer)
        if 0 <= i < j:
            return s[i : j + 1]
    return s


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
