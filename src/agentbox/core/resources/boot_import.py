"""Boot-time importer for the central resource repository.

Backward-compatible re-exports — implementation moved to ``boot/`` subpackage.
"""

from __future__ import annotations

from agentbox.core.resources.boot import (
    import_composition_references,
    import_one_skill,
    import_repo_resources,
    resolve_skill_roots,
    sweep_workspace_skill_bindings,
)

__all__ = [
    "import_composition_references",
    "import_one_skill",
    "import_repo_resources",
    "resolve_skill_roots",
    "sweep_workspace_skill_bindings",
]
