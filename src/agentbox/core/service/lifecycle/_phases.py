"""boot_import_resources sub-phases.

Private — only ``startup.boot_import_resources`` orders these.
Splitting them out keeps cyclomatic complexity in check.
"""

from __future__ import annotations

import logging
from typing import Any

from agentbox.core.config import Settings
from agentbox.core.data import ProjectManifest
from agentbox.core.resources.boot import (
    import_composition_references,
    import_repo_resources,
    sweep_workspace_skill_bindings,
)
from agentbox.core.resources.migration import (
    migrate_shared_resources_to_repo,
)
from agentbox.core.service.lifecycle.report import StartupReport
from agentbox.core.service.lifecycle._utils import _error

_log = logging.getLogger(__name__)


def _phase_import_repo(db: Any, settings: Settings) -> StartupReport:
    try:
        summary = import_repo_resources(
            db.resources, db.resource_versions, settings.project_root
        )
    except Exception as exc:
        _log.exception("repo-resource boot import failed")
        return _error("import_repo_resources", exc)
    if summary["created"] or summary["updated"]:
        _log.info(
            "boot-import repo_resources: created=%d updated=%d "
            "skipped=%d failed=%d",
            summary["created"],
            summary["updated"],
            summary["skipped"],
            summary["failed"],
        )
    return StartupReport(
        resources_created=int(summary.get("created", 0)),
        resources_updated=int(summary.get("updated", 0)),
    )


def _phase_legacy_migration(db: Any) -> StartupReport:
    try:
        report = migrate_shared_resources_to_repo(
            db.shared_resources, db.resources, db.resource_versions
        )
        summary = report.summary()
    except Exception as exc:
        _log.exception("legacy shared_resources sweep failed")
        return _error("migrate_shared_resources_to_repo", exc)
    if summary["migrated"] or summary["failed"]:
        _log.info("legacy shared_resources sweep: %s", summary)
    else:
        _log.debug("legacy shared_resources sweep: %s", summary)
    return StartupReport()


def _phase_workspace_bindings(
    db: Any, manifest: ProjectManifest | None
) -> StartupReport:
    try:
        summary = sweep_workspace_skill_bindings(
            db.resources, db.workspace_file_resource_bindings, manifest
        )
    except Exception as exc:
        _log.exception("workspace skill binding sweep failed")
        return _error("sweep_workspace_skill_bindings", exc)
    if summary["bindings_added"]:
        _log.info(
            "boot-import workspace bindings: wired %d workspace(s), "
            "%d binding(s)",
            summary["workspaces_wired"],
            summary["bindings_added"],
        )
    return StartupReport(
        workspaces_wired=int(summary.get("workspaces_wired", 0)),
        workspace_bindings_added=int(summary.get("bindings_added", 0)),
    )


def _phase_composition_refs(
    db: Any,
    settings: Settings,
    manifest: ProjectManifest | None,
) -> StartupReport:
    try:
        summary = import_composition_references(
            db.resources,
            db.resource_versions,
            db.agent_prompt_resource_bindings,
            settings.project_root,
            manifest,
        )
    except Exception as exc:
        _log.exception("composition refs import failed")
        return _error("import_composition_references", exc)
    if summary["bindings_added"]:
        _log.info(
            "boot-import composition refs: wired %d agent(s), "
            "%d resource(s), %d binding(s)",
            summary["agents_wired"],
            summary["resources_created"],
            summary["bindings_added"],
        )
    return StartupReport(
        composition_agents_wired=int(summary.get("agents_wired", 0)),
        composition_bindings_added=int(summary.get("bindings_added", 0)),
    )



