"""RunManager — run lifecycle operations."""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, update as sa_update

from agentbox.core.constants import RunStatus as RS
from agentbox.core.db.utils import now_iso
from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.runs.run import Run


class RunManager(Manager[Run]):
    """Manager for the ``runs`` table with run lifecycle operations."""

    model = Run

    def finish(
        self,
        run_id: str,
        status: str,
        output: str | None = None,
        error: str | None = None,
        finished_at: str | None = None,
    ) -> Run | None:
        """Mark a run as finished with status, output, error, and finish time."""
        values: dict[str, Any] = {"status": status}
        if output is not None:
            values["output"] = output
        if error is not None:
            values["error"] = error
        if finished_at is not None:
            values["finished_at"] = finished_at

        stmt = sa_update(Run).where(getattr(Run, "id") == run_id).values(**values)
        self._query(stmt)
        return self.get(run_id)

    def reap_orphans(
        self,
        reason: str = "orphaned: agentbox process restarted before run finished",
    ) -> int:
        """Mark all ``running`` rows as ``incomplete`` (startup reaper).

        Returns the number of rows affected.
        """
        stmt = (
            sa_update(Run)
            .where(
                getattr(Run, "status") == RS.RUNNING.value,
                getattr(Run, "finished_at").is_(None),  # sqlalchemy: Column.is_() not in stubs
            )
            .values(
                status=RS.INCOMPLETE.value,
                error=func.coalesce(Run.error, "").op("||")(reason),
                finished_at=now_iso(),
            )
        )
        result = self._query(stmt)
        return result.rowcount
