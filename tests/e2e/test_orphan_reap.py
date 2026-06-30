"""Startup recovery: 'running' rows from a prior process must be reaped.

The executor task owning a run dies with the process. After a restart
no task can possibly still own those rows, so SessionStore reaps them
on init. Without this, the UI shows runs ticking up forever (see the
real-world incident with run 9d92b4d0...).
"""

from __future__ import annotations

from pathlib import Path

from agentbox.core.db import SessionStore
from agentbox.core.db.schema import runs


def test_reap_marks_orphaned_running_rows_as_incomplete(tmp_path: Path) -> None:
    db = tmp_path / "agentbox.sqlite"
    store = SessionStore(db)
    rid = store.create_run("draft_writer", "{}", "/tmp/wd", "/tmp/t.jsonl")
    # row is in 'running' — simulate process death by dropping the store

    # New store on the same DB triggers reap on init.
    fresh = SessionStore(db)
    rec = fresh.get_run(rid)
    assert rec is not None
    # Orphan-reaped rows go to ``incomplete`` — the container died, the
    # agent itself didn't fail (which would be ``error`` / ``failed``).
    # ``incomplete`` is reserved for runs that were interrupted before
    # they could finish.
    assert rec.status == "incomplete"
    assert rec.finished_at is not None
    assert "orphaned" in (rec.error or "")


def test_reap_leaves_finished_runs_alone(tmp_path: Path) -> None:
    db = tmp_path / "agentbox.sqlite"
    store = SessionStore(db)
    ok_id = store.create_run("a", "{}", "/tmp/wd", "/tmp/t.jsonl")
    err_id = store.create_run("a", "{}", "/tmp/wd", "/tmp/t.jsonl")
    store.finish_run(ok_id, ok=True, output="done")
    store.finish_run(err_id, ok=False, error="real failure")

    SessionStore(db)  # re-init triggers reap
    ok_row = store.get_run(ok_id)
    err_row = store.get_run(err_id)
    assert ok_row is not None and ok_row.status == "ok"
    assert err_row is not None and err_row.status == "error"
    assert err_row.error == "real failure"  # untouched


def test_reap_preserves_existing_error_text(tmp_path: Path) -> None:
    """If a 'running' row somehow has prior error text, reap appends, not replaces."""
    db = tmp_path / "agentbox.sqlite"
    store = SessionStore(db)
    rid = store.create_run("a", "{}", "/tmp/wd", "/tmp/t.jsonl")
    # Manually inject prior error text on a still-running row.
    with store.engine.begin() as conn:
        conn.execute(
            runs.update().where(runs.c.id == rid).values(error="warn: slow tool ")
        )

    SessionStore(db)  # re-init reaps
    rec = store.get_run(rid)
    assert rec is not None
    assert rec.error is not None
    assert "warn: slow tool" in rec.error
    assert "orphaned" in rec.error
