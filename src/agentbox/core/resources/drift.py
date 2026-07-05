"""Resource drift detection and prompt-binding proposal utilities.

Boot-time and on-demand utilities for detecting prompt marker references
and proposing resource bindings. All operations are idempotent.
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

from agentbox.core.db import ResourceManager, ResourceVersionManager

logger = logging.getLogger(__name__)

_RESOURCE_MARKER_RE = re.compile(r"\{\{resource:([a-zA-Z0-9_\-./]+)\}\}")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _blobs_hash(filename: str, data: bytes) -> str:
    """Compute the same hash as ResourcesMixin._hash_blobs for one blob."""
    h = hashlib.sha256()
    h.update(filename.encode("utf-8"))
    h.update(b"\x00")
    h.update(hashlib.sha256(data).digest())
    h.update(b"\x00")
    return h.hexdigest()


def extract_prompt_markers(prompt_text: str) -> list[str]:
    """Return all ``{{resource:<marker>}}`` marker names found in *prompt_text*."""
    return _RESOURCE_MARKER_RE.findall(prompt_text)


def propose_prompt_bindings(
    resources: ResourceManager,
    agent_id: str,
    prompt_text: str,
) -> list[dict]:
    """For each ``{{resource:marker}}`` in *prompt_text*, check if a resource
    with the same slug exists and return proposed bindings.

    Does NOT write to the DB — callers decide whether to apply.
    Returns list of dicts: {marker, resource_id, resource_slug, mode}.
    """
    markers = extract_prompt_markers(prompt_text)
    if not markers:
        return []

    proposals = []
    for marker in markers:
        resource = resources.get_by_slug(marker)
        if resource is None:
            continue
        proposals.append(
            {
                "marker": marker,
                "resource_id": resource["id"],
                "resource_slug": marker,
                "mode": "embed",
            }
        )
    return proposals


def detect_resource_hash_mismatches(
    resources: ResourceManager,
    resource_versions: ResourceVersionManager,
    documents_dir: Path,
) -> list[dict]:
    """Compare each active resource version's hash against its on-disk source.

    Returns drift entries for resources whose active version content hash
    does not match the current file bytes.
    Each entry: {slug, resource_id, version_id, stored_hash, disk_hash, path}.
    """
    if not documents_dir.exists():
        return []

    mismatches = []
    for path in sorted(documents_dir.rglob("*")):
        if not path.is_file():
            continue
        slug = path.stem
        resource = resources.get_by_slug(slug)
        if resource is None:
            continue
        active = resource_versions.get_active_version(resource["id"])
        if active is None:
            continue
        stored_hash = active.get("content_hash")
        disk_hash = _blobs_hash(path.name, path.read_bytes())
        if stored_hash != disk_hash:
            mismatches.append(
                {
                    "slug": slug,
                    "resource_id": resource["id"],
                    "version_id": active["id"],
                    "stored_hash": stored_hash,
                    "disk_hash": disk_hash,
                    "path": str(path),
                }
            )
    return mismatches
