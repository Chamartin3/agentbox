"""Boot-time single-resource import helpers."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path

from agentbox.core.data.constants import ResourceType
from agentbox.core.data import hash_blobs
from agentbox.core.db import ResourceManager, ResourceVersionManager
from agentbox.core.resources.importers.base import ImporterContext, ResourceImporter
from agentbox.core.resources.importers.skill import SkillImporter

logger = logging.getLogger(__name__)


def import_one_skill(
    resources: ResourceManager,
    resource_versions: ResourceVersionManager,
    skill_dir: Path,
    root: Path,
) -> tuple[str, str]:
    name = skill_dir.name
    slug = f"skill:{name}"
    try:
        rel = skill_dir.relative_to(root)
        desc = f"Imported from {rel}"
    except ValueError:
        desc = f"Imported from {skill_dir}"
    action, _ = _import_one(
        resources, resource_versions,
        slug=slug, type_=ResourceType.SKILL, display_name=name,
        description=desc, importer=SkillImporter(root=skill_dir), tags=("skill", name),
        use_suggested=True,
    )
    return action, slug


def _import_one(
    resources: ResourceManager,
    resource_versions: ResourceVersionManager,
    *,
    slug: str,
    type_: ResourceType | str,
    display_name: str,
    description: str,
    importer: ResourceImporter,
    tags: Iterable[str] = (),
    metadata_extra: dict | None = None,
    use_suggested: bool = False,
) -> tuple[str, str]:
    ctx = ImporterContext(actor="boot_sweep", changelog="imported from manifest layout")
    result = importer.run(ctx)
    # Skills carry a real name/description in their SKILL.md frontmatter;
    # prefer those over the "Imported from <path>" placeholder. Opt-in so
    # host_path doc/folder imports keep their caller-provided display names.
    if use_suggested:
        display_name = result.suggested_display_name or display_name
        description = result.suggested_description or description
    content_hash = hash_blobs((b[0], b[1]) for b in result.blobs)
    merged_metadata = dict(result.metadata or {})
    if metadata_extra:
        merged_metadata.update(metadata_extra)
    existing = resources.get_by_slug(slug)
    if existing is not None:
        updates: dict = {}
        if existing.get("type") != type_:
            updates["type"] = type_
        if use_suggested:
            if existing.get("display_name") != display_name:
                updates["display_name"] = display_name
            if existing.get("description") != description:
                updates["description"] = description
        if updates:
            resources.update_resource(existing["id"], **updates)
        active = resource_versions.get_active_version(existing["id"])
        if active and active.get("content_hash") == content_hash:
            return "skipped", slug
        resource_versions.import_version(
            existing["id"], result.blobs, import_source="toml_migration",
            changelog="updated from manifest layout", source_metadata=result.source_metadata,
            metadata=merged_metadata or None,
        )
        return "updated", slug
    row = resources.create_resource(
        slug=slug, type=type_, display_name=display_name, description=description,
        tags=list(tags) or None,
    )
    resource_versions.import_version(
        row["id"], result.blobs, import_source="toml_migration",
        changelog="initial import from manifest layout", source_metadata=result.source_metadata,
        metadata=merged_metadata or None,
    )
    return "created", slug
