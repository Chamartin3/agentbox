"""Public API for composition-to-bindings migration."""

from agentbox.core.resources.legacy_composition._migrate import (
    migrate_composition_to_bindings,
)
from agentbox.core.resources.legacy_composition._report import (
    CompositionMigrationReport,
)

__all__ = [
    "CompositionMigrationReport",
    "migrate_composition_to_bindings",
]
