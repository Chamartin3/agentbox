"""RunnerProfileManager — runner backend profile CRUD."""
from __future__ import annotations

from sqlalchemy import select

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.engines.runner_profile import RunnerProfile


class RunnerProfileManager(Manager[RunnerProfile]):
    """Manager for the ``runner_profiles`` table."""

    model = RunnerProfile

    def get_default(self) -> RunnerProfile | None:
        """Return the system-default runner profile, or None."""
        stmt = (
            select(RunnerProfile)
            .where(
                getattr(RunnerProfile, "is_system_default") == 1,
                getattr(RunnerProfile, "is_enabled") == 1,
            )
            .limit(1)
        )
        return self._scalar(stmt)

    def find_by_backend(self, backend: str) -> list[RunnerProfile]:
        """Return all enabled profiles for a given backend name."""
        return self.find(backend=backend, is_enabled=1)
