"""Store operations for composition-to-bindings migration."""

from __future__ import annotations

import hashlib

from agentbox.core.db import ResourceManager, ResourceVersionManager
from agentbox.core.resources.legacy_composition._helpers import (
    mime_for,
    parse_tags,
    slug_for,
)
from agentbox.core.resources.legacy_composition._report import (
    MIGRATION_ACTOR,
    CompositionMigrationReport,
)


def get_or_create_resource(
    resources: ResourceManager,
    resource_versions: ResourceVersionManager,
    *,
    content_text: str,
    type_: str,
    relative_path: str,
    agent_id: str,
    report: CompositionMigrationReport,
) -> str:
    """Get-or-create a repo resource keyed by content hash. Returns resource_id."""
    content_bytes = content_text.encode("utf-8")
    sha_full = hashlib.sha256(content_bytes).hexdigest()
    sha12 = sha_full[:12]
    slug = slug_for(type_, sha12)
    agent_tag = f"agent:{agent_id}"

    existing = resources.get_by_slug(slug)
    if existing is not None:
        tags = parse_tags(existing.get("tags"))
        if agent_tag not in tags:
            resources.update_resource(existing["id"], tags=[*tags, agent_tag])
        return existing["id"]

    pretty_kind = (
        "input schema"
        if "input_schema" in relative_path
        else "output schema"
        if "output_schema" in relative_path
        else relative_path
    )
    display = (
        f"{agent_id} {pretty_kind}"
        if type_ == "schema"
        else f"{agent_id} {relative_path}"
    )
    res = resources.create_resource(
        slug=slug,
        type=type_,
        display_name=display,
        description=f"Migrated from {agent_id}: {relative_path}",
        tags=["migrated", agent_tag],
        created_by=MIGRATION_ACTOR,
    )
    report.resources_created += 1
    resource_versions.import_version(
        res["id"],
        [("", content_bytes, mime_for(type_), content_text)],
        import_source="toml_migration",
        changelog="migrated from agent composition",
        source_metadata={
            "agent_id": agent_id,
            "relative_path": relative_path,
            "content_sha256": sha_full,
        },
        created_by=MIGRATION_ACTOR,
    )
    report.versions_created += 1
    return res["id"]
