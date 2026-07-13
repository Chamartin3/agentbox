"""Engine lifecycle for agentbox.core.db.

Port of the engine creation and startup lifecycle from
``agentbox.core.db.store._CoreStore`` — creates the SQLAlchemy ``Engine``,
runs Alembic migrations on startup, and reaps orphaned runs.

This module is internal. Only ``Database`` (via ``core/db/database.py``)
calls ``init_engine``.
"""
from __future__ import annotations

import logging
from pathlib import Path

import agentbox
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func
from sqlalchemy.engine import Engine

from agentbox.core.data.constants import RunStatus
from agentbox.core.db.schema import runs
from agentbox.core.data._util import now_iso

# Used as fallback when Alembic is unavailable.
from agentbox.core.db.base.metadata import metadata  # noqa: F401

logger = logging.getLogger(__name__)


def init_engine(db_path: Path) -> Engine:
    """Create a SQLAlchemy Engine for ``db_path`` and run startup lifecycle.

    Steps:
    1. Ensure parent directory exists.
    2. Create engine (check_same_thread=False for threadpool safety).
    3. Run Alembic migrations (or fallback ``create_all``).
    4. Reap orphaned runs left from a previous process death.
    5. Dispose the startup engine connection to release the exclusive
       migration lock. The caller (``Database``) owns the final engine.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)

    engine: Engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )

    _run_alembic_migrations(engine, db_path)
    engine.dispose()

    # Re-create so the caller gets a fresh engine.
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    # NOTE: reaping is NOT done here. Every process that opens the DB calls
    # init_engine — including tool subprocesses (e.g. the agentbox-host-env MCP
    # server) spawned by a live run. Reaping on each engine init makes such a
    # subprocess mark the very run that spawned it as "orphaned" the moment it
    # uses a tool. The API server reaps real orphans on startup via
    # run_startup_tasks -> reap_orphan_runs (see api/app.py _on_startup).
    return engine


def _run_alembic_migrations(engine: Engine, db_path: Path) -> None:
    """Run pending Alembic migrations on startup.

    Falls back to ``metadata.create_all(engine)`` when Alembic is
    unavailable or the migrations directory is not found.
    """
    try:
        alembic_cfg = Config()
        alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

        candidates = [
            Path(agentbox.__file__).parent.parent / "alembic",
            Path(agentbox.__file__).parent.parent.parent / "alembic",
            Path.cwd() / "alembic",
        ]
        migrations_dir: Path | None = None
        for c in candidates:
            if c.is_dir():
                migrations_dir = c
                break

        if migrations_dir is not None:
            alembic_cfg.set_main_option("script_location", str(migrations_dir))
            command.upgrade(alembic_cfg, "head")
            logger.debug("alembic: upgraded to head")
        else:
            logger.warning(
                "alembic: migrations directory not found in %s — falling back to create_all",
                [str(c) for c in candidates],
            )
            metadata.create_all(engine)
    except ImportError:
        logger.debug("alembic: not installed — falling back to create_all")
        metadata.create_all(engine)
    except Exception:
        logger.exception("alembic: migration failed, falling back to create_all")
        metadata.create_all(engine)


def _reap_orphaned_runs(engine: Engine) -> None:
    """Mark any pre-existing 'running' rows as ``incomplete`` on startup.

    Port of ``_CoreStore._reap_orphaned_runs`` — see that method for the
    full rationale. We import the ``runs`` table directly from the legacy
    schema module since the new models catalog tables may not exist at
    the time this runs.
    """
    reason = "orphaned: agentbox process restarted before run finished"
    with engine.begin() as conn:
        conn.execute(
            runs.update()
            .where(
                runs.c.status == RunStatus.RUNNING.value,
                runs.c.finished_at.is_(None),
            )
            .values(
                status=RunStatus.INCOMPLETE.value,
                error=func.coalesce(runs.c.error, "") + reason,
                finished_at=now_iso(),
            )
        )
        conn.execute(
            runs.update()
            .where(runs.c.status == "stopped")
            .values(status=RunStatus.INCOMPLETE.value)
        )
