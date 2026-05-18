"""Resource migration sweeps (Plan 08 Phase 8).

Boot-time sweeps that import existing on-disk content into the resource
repository and propose bindings for prompt markers. Designed to be called
once at startup from the executor or app factory — all operations are
idempotent.
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from agentbox.core.constants import ResourceType

if TYPE_CHECKING:
    from agentbox.core.data.store import SessionStore

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


def _blob_tuple(filename: str, data: bytes) -> tuple[str, bytes, str | None, str | None]:
    mime = "text/plain" if filename.endswith((".md", ".txt")) else None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = None
    return (filename, data, mime, text)


def import_manifest_documents(
    store: SessionStore,
    documents_dir: Path,
) -> int:
    """Import every file under ``documents_dir`` as a document resource version.

    Idempotent: skips files whose content hash already matches the active
    version. Returns the number of new versions created.
    """
    if not documents_dir.exists():
        return 0

    imported = 0
    for path in sorted(documents_dir.rglob("*")):
        if not path.is_file():
            continue
        slug = path.stem
        data = path.read_bytes()
        content_hash = _blobs_hash(path.name, data)

        existing = store.get_repo_resource_by_slug(slug)
        if existing is not None:
            active = store.get_active_repo_version(existing["id"])
            if active is not None and active.get("content_hash") == content_hash:
                continue
            store.import_repo_version(
                existing["id"],
                [_blob_tuple(path.name, data)],
                import_source="toml_migration",
                changelog="updated from manifest documents",
            )
            imported += 1
            logger.info("resource-drift: updated document resource %r", slug)
        else:
            row = store.create_repo_resource(
                slug=slug,
                type=ResourceType.DOCUMENT,
                display_name=slug,
                description=f"Imported from {path.name}",
            )
            store.import_repo_version(
                row["id"],
                [_blob_tuple(path.name, data)],
                import_source="toml_migration",
                changelog="imported from manifest documents",
            )
            imported += 1
            logger.info("resource-drift: imported document resource %r", slug)

    return imported


def import_manifest_skills(
    store: SessionStore,
    skills_dir: Path,
) -> int:
    """Import *.md files from ``skills_dir`` as skill resources.

    Same idempotency logic as :func:`import_manifest_documents`.
    Returns the number of new versions created.
    """
    if not skills_dir.exists():
        return 0

    imported = 0
    for path in sorted(skills_dir.rglob("*.md")):
        if not path.is_file():
            continue
        slug = f"skill/{path.stem}"
        data = path.read_bytes()
        content_hash = _blobs_hash(path.name, data)

        existing = store.get_repo_resource_by_slug(slug)
        if existing is not None:
            active = store.get_active_repo_version(existing["id"])
            if active is not None and active.get("content_hash") == content_hash:
                continue
            store.import_repo_version(
                existing["id"],
                [_blob_tuple(path.name, data)],
                import_source="toml_migration",
                changelog="updated from manifest skills",
            )
            imported += 1
            logger.info("resource-drift: updated skill resource %r", slug)
        else:
            row = store.create_repo_resource(
                slug=slug,
                type=ResourceType.SKILL,
                display_name=path.stem,
                description=f"Imported from {path.name}",
            )
            store.import_repo_version(
                row["id"],
                [_blob_tuple(path.name, data)],
                import_source="toml_migration",
                changelog="imported from manifest skills",
            )
            imported += 1
            logger.info("resource-drift: imported skill resource %r", slug)

    return imported


def extract_prompt_markers(prompt_text: str) -> list[str]:
    """Return all ``{{resource:<marker>}}`` marker names found in *prompt_text*."""
    return _RESOURCE_MARKER_RE.findall(prompt_text)


def propose_prompt_bindings(
    store: SessionStore,
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
        resource = store.get_repo_resource_by_slug(marker)
        if resource is None:
            continue
        proposals.append({
            "marker": marker,
            "resource_id": resource["id"],
            "resource_slug": marker,
            "mode": "embed",
        })
    return proposals


def detect_resource_hash_mismatches(
    store: SessionStore,
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
        resource = store.get_repo_resource_by_slug(slug)
        if resource is None:
            continue
        active = store.get_active_repo_version(resource["id"])
        if active is None:
            continue
        stored_hash = active.get("content_hash")
        disk_hash = _blobs_hash(path.name, path.read_bytes())
        if stored_hash != disk_hash:
            mismatches.append({
                "slug": slug,
                "resource_id": resource["id"],
                "version_id": active["id"],
                "stored_hash": stored_hash,
                "disk_hash": disk_hash,
                "path": str(path),
            })
    return mismatches


def run_all_sweeps(
    store: SessionStore,
    *,
    documents_dir: Path | None = None,
    skills_dir: Path | None = None,
) -> dict:
    """Run all boot-time resource sweeps and return a summary dict."""
    docs_imported = 0
    skills_imported = 0

    if documents_dir is not None:
        docs_imported = import_manifest_documents(store, documents_dir)

    if skills_dir is not None:
        skills_imported = import_manifest_skills(store, skills_dir)

    return {
        "docs_imported": docs_imported,
        "skills_imported": skills_imported,
    }
