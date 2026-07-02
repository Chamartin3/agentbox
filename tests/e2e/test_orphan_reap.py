"""Startup recovery: 'running' rows from a prior process must be reaped.

The executor task owning a run dies with the process. After a restart
no task can possibly still own those rows, so the run manager reaps them
explicitly via ``reap_orphans()``. Without this, the UI shows runs ticking
up forever (see the real-world incident with run 9d92b4d0...).
"""

from __future__ import annotations

import uuid
from pathlib import Path

from agentbox.core.data import now_iso
from agentbox.core.db.database import Database
from agentbox.core.db.schema import runs


def _make_run(store: Database, agent_id: str) -> str:
    rid = uuid.uuid4().hex
    store.runs.create(
        id=rid,
        agent_id=agent_id,
        status="running",
        input="{}",
        workdir="/tmp/wd",
        transcript_path="/tmp/t.jsonl",
        created_at=now_iso(),
    )
    return rid


def test_reap_marks_orphaned_running_rows_as_incomplete(tmp_path: Path) -> None:
    store = Database(tmp_path / "agentbox.sqlite")
    rid = _make_run(store, "draft_writer")
    # row is in 'running' — simulate process death by calling the reaper

    store.runs.reap_orphans()
    rec = store.runs.get(rid)
    assert rec is not None
    # Orphan-reaped rows go to ``incomplete`` — the container died, the
    # agent itself didn't fail (which would be ``error`` / ``failed``).
    # ``incomplete`` is reserved for runs that were interrupted before
    # they could finish.
    assert rec.status == "incomplete"
    assert rec.finished_at is not None
    assert "orphaned" in (rec.error or "")


def test_reap_leaves_finished_runs_alone(tmp_path: Path) -> None:
    store = Database(tmp_path / "agentbox.sqlite")
    ok_id = _make_run(store, "a")
    err_id = _make_run(store, "a")
    store.runs.finish_full(run_id=ok_id, ok=True, output="done")
    store.runs.finish_full(run_id=err_id, ok=False, error="real failure")

    store.runs.reap_orphans()  # explicit reap; finished rows must be unaffected
    ok_row = store.runs.get(ok_id)
    err_row = store.runs.get(err_id)
    assert ok_row is not None and ok_row.status == "ok"
    assert err_row is not None and err_row.status == "error"
    assert err_row.error == "real failure"  # untouched


def test_reap_preserves_existing_error_text(tmp_path: Path) -> None:
    """If a 'running' row somehow has prior error text, reap appends, not replaces."""
    store = Database(tmp_path / "agentbox.sqlite")
    rid = _make_run(store, "a")
    # Manually inject prior error text on a still-running row.
    with store.engine.begin() as conn:
        conn.execute(
            runs.update().where(runs.c.id == rid).values(error="warn: slow tool ")
        )

    store.runs.reap_orphans()  # explicit reap
    rec = store.runs.get(rid)
    assert rec is not None
    assert rec.error is not None
    assert "warn: slow tool" in rec.error
    assert "orphaned" in rec.error
