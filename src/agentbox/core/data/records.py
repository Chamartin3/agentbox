"""DB return-shape dataclasses and row mappers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.engine import Row


@dataclass
class RunRecord:
    id: str
    agent_id: str
    session_id: str | None
    status: str
    input: str
    output: str | None
    error: str | None
    workdir: str | None
    transcript_path: str | None
    created_at: str
    finished_at: str | None
    config_digest: str | None = None
    agent_version_id: int | None = None
    composition_snapshot: str | None = None
    rendered_prompt: str | None = None
    variables: str | None = None
    validation_status: str | None = None
    validation_errors: str | None = None


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def row_to_run(row: Row) -> RunRecord:
    m = row._mapping
    return RunRecord(
        id=m["id"],
        agent_id=m["agent_id"],
        session_id=m["session_id"],
        status=m["status"],
        input=m["input"],
        output=m["output"],
        error=m["error"],
        workdir=m["workdir"],
        transcript_path=m["transcript_path"],
        created_at=m["created_at"],
        finished_at=m["finished_at"],
        config_digest=m.get("config_digest"),
        agent_version_id=m.get("agent_version_id"),
        composition_snapshot=m.get("composition_snapshot"),
        rendered_prompt=m.get("rendered_prompt"),
        variables=m.get("variables"),
        validation_status=m.get("validation_status"),
        validation_errors=m.get("validation_errors"),
    )
