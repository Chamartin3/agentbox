"""boot_import_resources sub-phases.

Private — only ``startup.boot_import_resources`` orders these.
Splitting them out keeps cyclomatic complexity in check.
"""

from __future__ import annotations

import logging
from typing import Any

from agentbox.core.config import Settings
from agentbox.core.resources.boot import (
    import_repo_resources,
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
