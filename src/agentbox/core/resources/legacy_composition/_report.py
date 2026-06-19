"""Report dataclass and constants for composition-to-bindings migration."""

from __future__ import annotations

from dataclasses import dataclass, field


USER_TEMPLATE_MARKER = "user_template"
USER_TEMPLATE_MODE = "inline"
MIGRATION_REASON = "boot: migrate composition slots to bindings"
MIGRATION_ACTOR = "composition_migration"


@dataclass
class CompositionMigrationReport:
    agents_migrated: list[str] = field(default_factory=list)
    agents_skipped_no_composition: list[str] = field(default_factory=list)
    agents_skipped_fully_bound: list[str] = field(default_factory=list)
    bindings_created: int = 0
    resources_created: int = 0
    versions_created: int = 0
    failed: list[tuple[str, str]] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "agents_migrated": len(self.agents_migrated),
            "agents_skipped_no_composition": len(self.agents_skipped_no_composition),
            "agents_skipped_fully_bound": len(self.agents_skipped_fully_bound),
            "bindings_created": self.bindings_created,
            "resources_created": self.resources_created,
            "versions_created": self.versions_created,
            "failed": len(self.failed),
        }
