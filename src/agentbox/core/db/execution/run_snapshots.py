"""Run snapshot write mixin — composition, resource, and runner snapshots."""

from __future__ import annotations

import warnings

import json as _json

from sqlalchemy.engine import Engine

from agentbox.core.db.execution.snapshots import McpSnapshot, ResourceSnapshotEntry, RunnerSnapshot
from agentbox.core.db.schema import runs


class RunSnapshotsMixin:
    """Run snapshot write methods requiring ``self.engine: Engine``."""

    engine: Engine

    def save_run_snapshot(
        self,
        run_id: str,
        rendered_prompt: dict,
        variables: dict,
        validation_status: str,
        validation_errors: list[str],
        composition_snapshot: dict | None = None,
    ) -> None:
        warnings.warn(
            "RunSnapshotsMixin.save_run_snapshot is deprecated; use db.runs (snapshot methods) manager instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        values: dict = {
            "rendered_prompt": _json.dumps(rendered_prompt),
            "variables": _json.dumps(variables),
            "validation_status": validation_status,
            "validation_errors": _json.dumps(validation_errors),
        }
        if composition_snapshot is not None:
            values["composition_snapshot"] = _json.dumps(composition_snapshot)
        with self.engine.begin() as conn:
            conn.execute(runs.update().where(runs.c.id == run_id).values(**values))

    def save_run_composition(
        self,
        run_id: str,
        composition_snapshot: dict | None,
        rendered_prompt: dict | None,
        variables: dict | None,
    ) -> None:
        warnings.warn(
            "RunSnapshotsMixin.save_run_composition is deprecated; use db.runs (snapshot methods) manager instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        values: dict = {}
        if composition_snapshot is not None:
            values["composition_snapshot"] = _json.dumps(composition_snapshot)
        if rendered_prompt is not None:
            values["rendered_prompt"] = _json.dumps(rendered_prompt)
        if variables is not None:
            values["variables"] = _json.dumps(variables)

        if values:
            with self.engine.begin() as conn:
                conn.execute(runs.update().where(runs.c.id == run_id).values(**values))

    def save_resource_snapshots(
        self,
        run_id: str,
        *,
        resource_snapshot: list[ResourceSnapshotEntry] | None = None,
        mcp_snapshot: McpSnapshot | None = None,
    ) -> None:
        warnings.warn(
            "RunSnapshotsMixin.save_resource_snapshots is deprecated; use db.runs (snapshot methods) manager instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        values: dict = {}
        if resource_snapshot is not None:
            values["resource_snapshot"] = _json.dumps(resource_snapshot)
        if mcp_snapshot is not None:
            values["mcp_snapshot"] = _json.dumps(mcp_snapshot)
        if values:
            with self.engine.begin() as conn:
                conn.execute(runs.update().where(runs.c.id == run_id).values(**values))

    def save_run_runner_snapshot(
        self,
        run_id: str,
        runner_snapshot: RunnerSnapshot,
    ) -> None:
        """Persist the runner config resolved at dispatch time.

        Append-only — write once, never updated. This is the historical
        record of what backend/model/timeout actually ran the agent.
        Mutating the bound profile or rebinding the agent must not affect
        a previously persisted snapshot.
        """
        warnings.warn(
            "RunSnapshotsMixin.save_run_runner_snapshot is deprecated; use db.runs (snapshot methods) manager instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        with self.engine.begin() as conn:
            conn.execute(
                runs.update()
                .where(
                    runs.c.id == run_id,
                    runs.c.runner_snapshot.is_(None),
                )
                .values(runner_snapshot=_json.dumps(runner_snapshot))
            )
