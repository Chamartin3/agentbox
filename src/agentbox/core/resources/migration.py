"""One-shot sweep: shared_resources → unified resources table.

Moves every active row in the legacy ``shared_resources`` table into the
unified ``resources`` repository with the new typed taxonomy:

- ``output_schema``, ``input_schema``  → ``schema``
- ``user_template``, ``system_fragment`` → ``document`` (with metadata.role)
- ``reference``                          → ``document``
- ``skill``                              → ``skill``
- ``mcp_server``                         → kept in ``shared_resources`` (out of scope)

Idempotent: runs that find an existing slug match skip the row. Does not
delete legacy rows — the legacy table is left in place until the
``/api/resources`` router is removed in a later release.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentbox.core.db import (
        ResourceManager,
        ResourceVersionManager,
        SharedResourceManager,
    )

KIND_TO_TYPE = {
    "output_schema": "schema",
    "input_schema": "schema",
    "user_template": "document",
    "system_fragment": "document",
    "reference": "document",
    "skill": "skill",
}

SKIPPED_KINDS = {"mcp_server"}


@dataclass
class MigrationReport:
    migrated: list[str] = field(default_factory=list)
    skipped_existing: list[str] = field(default_factory=list)
    skipped_kinds: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "migrated": len(self.migrated),
            "skipped_existing": len(self.skipped_existing),
            "skipped_kinds": len(self.skipped_kinds),
            "failed": len(self.failed),
        }


def _slug_for(record) -> str:
    return f"legacy:{record.kind}:{record.id}"


def migrate_shared_resources_to_repo(
    shared_resources: SharedResourceManager,
    resources: ResourceManager,
    resource_versions: ResourceVersionManager,
) -> MigrationReport:
    """Walk active shared_resources and import each into the repo."""
    report = MigrationReport()
    legacy = shared_resources.list_active(limit=10_000)

    for rec in legacy:
        if rec.kind in SKIPPED_KINDS:
            report.skipped_kinds.append(rec.id)
            continue
        target_type = KIND_TO_TYPE.get(rec.kind)
        if not target_type:
            report.failed.append((rec.id, f"unknown kind {rec.kind!r}"))
            continue

        slug = _slug_for(rec)
        existing = next(
            (
                r
                for r in resources.list_resources(query=slug, limit=10)
                if r["slug"] == slug
            ),
            None,
        )
        if existing:
            report.skipped_existing.append(rec.id)
            continue

        try:
            created = resources.create_resource(
                slug=slug,
                type=target_type,
                display_name=rec.name,
                description=rec.description,
                tags=[*list(rec.tags), f"legacy_kind:{rec.kind}"],
            )
            content_bytes = (rec.content or rec.config_json or "").encode("utf-8")
            blobs: list[tuple[str, bytes, str | None, str | None]] = [
                ("", content_bytes, "text/plain", rec.content or rec.config_json)
            ]
            resource_versions.import_version(
                created["id"],
                blobs,
                import_source="toml_migration",
                changelog=f"migrated from shared_resources/{rec.kind}",
                source_metadata={
                    "legacy_id": rec.id,
                    "legacy_version": rec.version,
                    "legacy_kind": rec.kind,
                },
                metadata={"legacy_role": rec.kind}
                if target_type == "document"
                else None,
                draft=False,
                created_by=rec.author,
            )
            report.migrated.append(rec.id)
        except Exception as exc:  # capture but don't abort the sweep
            report.failed.append((rec.id, str(exc)))

    return report
