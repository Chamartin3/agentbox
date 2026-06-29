"""Boot-time single-resource import helpers."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from agentbox.core.constants import ResourceType
from agentbox.core.data import hash_blobs
from agentbox.core.resources.importers.base import ImporterContext
from agentbox.core.resources.importers.skill import SkillImporter

if TYPE_CHECKING:
    from agentbox.core.db import SessionStore

logger = logging.getLogger(__name__)


def import_one_skill(store: SessionStore, skill_dir: Path, root: Path) -> tuple[str, str]:
    name = skill_dir.name
    slug = f"skill:{name}"
    try:
        rel = skill_dir.relative_to(root)
        desc = f"Imported from {rel}"
    except ValueError:
        desc = f"Imported from {skill_dir}"
    action, _ = _import_one(
        store, slug=slug, type_=ResourceType.SKILL, display_name=name,
        description=desc, importer=SkillImporter(root=skill_dir), tags=("skill", name),
    )
    return action, slug


def _import_one(store: SessionStore, *, slug: str, type_: ResourceType | str, display_name: str, description: str, importer, tags: Iterable[str] = (), metadata_extra: dict | None = None) -> tuple[str, str]:
    ctx = ImporterContext(actor="boot_sweep", changelog="imported from manifest layout")
    result = importer.run(ctx)
    content_hash = hash_blobs((b[0], b[1]) for b in result.blobs)
    merged_metadata = dict(result.metadata or {})
    if metadata_extra:
        merged_metadata.update(metadata_extra)
    existing = store.get_repo_resource_by_slug(slug)
    if existing is not None:
        if existing.get("type") != type_:
            store.update_repo_resource(existing["id"], type=type_)
        active = store.get_active_repo_version(existing["id"])
        if active and active.get("content_hash") == content_hash:
            return "skipped", slug
        store.import_repo_version(
            existing["id"], result.blobs, import_source="toml_migration",
            changelog="updated from manifest layout", source_metadata=result.source_metadata,
            metadata=merged_metadata or None,
        )
        return "updated", slug
    row = store.create_repo_resource(slug=slug, type=type_, display_name=display_name, description=description, tags=list(tags) or None)
    store.import_repo_version(
        row["id"], result.blobs, import_source="toml_migration",
        changelog="initial import from manifest layout", source_metadata=result.source_metadata,
        metadata=merged_metadata or None,
    )
    return "created", slug
