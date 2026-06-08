"""Run CRUD mixin: create, finish, query, and orphan-reap runs."""

from __future__ import annotations

import json as _json
import uuid


from sqlalchemy.engine import Engine

from agentbox.core.constants import RunStatus
from agentbox.core.data.execution.records import RunRecord, row_to_run
from agentbox.core.data.schema import runs
from agentbox.core.data.utils import now_iso


class RunsMixin:
    """Run CRUD requiring ``self.engine: Engine``."""

    engine: Engine

    def create_run(
        self,
        agent_id: str,
        input_: str,
        workdir: str,
        transcript_path: str,
        session_id: str | None = None,
        config_digest: str | None = None,
        runner_profile_id: str | None = None,
    ) -> str:
        rid = uuid.uuid4().hex
        with self.engine.begin() as conn:
            conn.execute(
                runs.insert().values(
                    id=rid,
                    agent_id=agent_id,
                    session_id=session_id,
                    status=RunStatus.RUNNING.value,
                    input=input_,
                    workdir=workdir,
                    transcript_path=transcript_path,
                    created_at=now_iso(),
                    config_digest=config_digest,
                    runner_profile_id=runner_profile_id,
                )
            )
        return rid

    def finish_run(
        self,
        run_id: str,
        ok: bool,
        output: str | None = None,
        error: str | None = None,
        status: str | None = None,
        validation_status: str | None = None,
        validation_errors: list[str] | None = None,
        schema_validated_via: str | None = None,
    ) -> None:
        values: dict = {
            "status": status
            if status
            else (RunStatus.OK.value if ok else RunStatus.ERROR.value),
            "output": output,
            "error": error,
            "finished_at": now_iso(),
        }
        if validation_status is not None:
            values["validation_status"] = validation_status
        if validation_errors is not None:
            values["validation_errors"] = _json.dumps(validation_errors)
        if schema_validated_via is not None:
            values["schema_validated_via"] = schema_validated_via
        with self.engine.begin() as conn:
            conn.execute(
                runs.update()
                .where(
                    runs.c.id == run_id,
                    runs.c.status.in_((RunStatus.RUNNING.value,)),
                )
                .values(**values)
            )

    def set_run_conversation(
        self,
        run_id: str,
        conversation_format: str | None,
        conversation_uri: str | None = None,
    ) -> None:
        values: dict = {}
        if conversation_format is not None:
            values["conversation_format"] = conversation_format
        if conversation_uri is not None:
            values["conversation_uri"] = conversation_uri
        if values:
            with self.engine.begin() as conn:
                conn.execute(runs.update().where(runs.c.id == run_id).values(**values))

    def set_run_post_outcome(
        self,
        run_id: str,
        ok: bool,
        error_kind: str | None = None,
        errors: list[dict] | None = None,
    ) -> None:
        values: dict = {"post_status": "ok" if ok else "fail"}
        if errors is not None:
            values["post_errors"] = _json.dumps(
                {"error_kind": error_kind, "errors": errors}
            )
        with self.engine.begin() as conn:
            conn.execute(runs.update().where(runs.c.id == run_id).values(**values))

    def list_orphaned_unnotified_runs(self) -> list[RunRecord]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                runs.select()
                .where(
                    runs.c.error.like("%orphaned%"),
                    runs.c.post_status.is_(None),
                )
                .order_by(runs.c.finished_at.asc())
            ).fetchall()
        return [row_to_run(r) for r in rows]

    def reap_orphan_runs(self) -> int:
        with self.engine.begin() as conn:
            result = conn.execute(
                runs.update()
                .where(runs.c.status == RunStatus.RUNNING.value)
                .values(
                    status=RunStatus.INCOMPLETE.value,
                    error="orphaned: executor process restarted before run completed",
                    finished_at=now_iso(),
                )
            )
            return result.rowcount or 0

    def set_run_status(self, run_id: str, status: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(runs.update().where(runs.c.id == run_id).values(status=status))

    def get_run(self, run_id: str) -> RunRecord | None:
        with self.engine.connect() as conn:
            row = conn.execute(runs.select().where(runs.c.id == run_id)).first()
            return row_to_run(row) if row else None

    def list_runs(
        self, limit: int = 50, agent_id: str | None = None
    ) -> list[RunRecord]:
        stmt = runs.select().order_by(runs.c.created_at.desc()).limit(limit)
        if agent_id:
            stmt = stmt.where(runs.c.agent_id == agent_id)
        with self.engine.connect() as conn:
            return [row_to_run(r) for r in conn.execute(stmt)]
