"""Backward-compat shim — was a single file, now a subpackage.

Usage was:
    from agentbox.core.resources.composition_to_bindings import (
        migrate_composition_to_bindings,
    )

New import:
    from agentbox.core.resources.composition import (
        migrate_composition_to_bindings,
    )
"""

from agentbox.core.resources.composition import (  # noqa: F401
    CompositionMigrationReport,
    migrate_composition_to_bindings,
)
