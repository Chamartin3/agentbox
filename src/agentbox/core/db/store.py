"""SQLite-backed store for runs, sessions, transcripts, and usage.

Uses SQLAlchemy Core for schema + queries. We stay on Core (not the ORM)
because the data shapes are flat rows, the public API returns plain
dicts / dataclasses, and the analytics queries are conditional aggregates
that read more clearly as SQL expressions than as ORM relationships.

``SessionStore`` is composed from per-domain mixins:
- ``SessionsMixin``        — session CRUD
- ``RunCommentsMixin``     — run comment CRUD
- ``UsageMixin``           — usage record/query
- ``WebhooksMixin``        — webhook delivery logging
- ``RunPromptsMixin``      — run prompt capture
- ``RunSnapshotsMixin``    — composition, resource, and runner snapshots
- ``RunsMixin``            — run lifecycle CRUD
- ``AgentToolGrantsMixin`` — agent-scoped tool grant/revoke CRUD
- ``PromptVersionsMixin``  — draft/publish/rollback for prompt history
"""

from __future__ import annotations

import logging
from pathlib import Path

import agentbox
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func
from sqlalchemy.engine import Engine

from agentbox.core.constants import RunStatus
from agentbox.core.db.agents.events import AgentConfigEventsMixin
from agentbox.core.db.agents.sync import AgentSyncMixin
from agentbox.core.db.agents.grants import AgentToolGrantsMixin
from agentbox.core.db.agents.versions import AgentVersionsMixin
from agentbox.core.db.agents.prompts import PromptVersionsMixin
from agentbox.core.db.resources.crud import ResourcesMixin
from agentbox.core.db.resources.shared import SharedResourcesMixin
from agentbox.core.db.resources.bindings import ResourceBindingsMixin
# Execution mixins retired in plan 088 — ExecutionService now owns the run lifecycle.
# RunsMixin, SessionsMixin, RunCommentsMixin, UsageMixin, WebhooksMixin,
# RunPromptsMixin, RunSnapshotsMixin removed.
from agentbox.core.db.schema import (
    metadata,
    runs,
)
from agentbox.core.db.utils import now_iso
from agentbox.core.db.workspaces.crud import WorkspacesMixin
from agentbox.core.db.workspaces.env_docs import EnvDocsMixin
from agentbox.core.db.workspaces.host_env import HostEnvMixin
from agentbox.core.db.workspaces.mcp_discovery import McpDiscoveryMixin
from agentbox.core.db.workspaces.mcp_overrides import McpOverridesMixin
from agentbox.core.db.workspaces.runtime_permissions import RuntimePermissionsMixin
from agentbox.core.db.workspaces.templates import WorkenvTemplatesMixin

logger = logging.getLogger(__name__)


class _CoreStore:
    """Connection management + startup lifecycle for the session store.

    All domain CRUD is pushed into per-domain mixins. This class owns
    only the engine wiring, Alembic migrations, and the startup orphan-reap
    that must run before any domain code executes.
    """

    def __init__(self, db_path: Path, *, reap_orphans: bool = True) -> None:
        # reap_orphans: only the primary server process should reap. A
        # SECONDARY store opened against the same DB by a subprocess (e.g. the
        # host-env MCP tool server writing its audit log) must NOT reap — its
        # startup would otherwise mark the parent's still-running run as
        # orphaned. See _reap_orphaned_runs.
        self._reap_orphans = reap_orphans
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False — FastAPI dispatches sync handlers to a
        # threadpool, so the connection may travel across threads.
        # SQLAlchemy's pool serializes writes via the connection itself.
        self.engine: Engine = create_engine(
            f"sqlite:///{self.db_path}",
            connect_args={"check_same_thread": False},
            future=True,
        )
        self._init()

    def _init(self) -> None:
        self._run_alembic_migrations()
        self.engine.dispose()
        if self._reap_orphans:
            self._reap_orphaned_runs()

    def _run_alembic_migrations(self) -> None:
        """Run pending Alembic migrations on startup."""
        try:
            alembic_cfg = Config()
            alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{self.db_path}")

            # Find the migrations directory — check a few candidate paths so
            # both editable installs and built wheels work.
            candidates = [
                Path(agentbox.__file__).parent.parent / "alembic",
                Path(agentbox.__file__).parent.parent.parent / "alembic",
                Path.cwd() / "alembic",
            ]
            migrations_dir = None
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
                metadata.create_all(self.engine)
        except ImportError:
            logger.debug("alembic: not installed — falling back to create_all")
            metadata.create_all(self.engine)
        except Exception:
            logger.exception("alembic: migration failed, falling back to create_all")
            metadata.create_all(self.engine)

    def _reap_orphaned_runs(self) -> None:
        """Mark any pre-existing 'running' rows as ``incomplete`` on startup.

        Why: the in-process executor task that owns a run dies with the
        container. If the process is killed (or `_run` crashes after the
        runner loop but before `finish_run`), the row sits as 'running'
        forever. On startup no executor task can possibly still own those
        rows, so reap them as ``incomplete`` — the agent itself didn't
        fail to do its task; the container went away before the agent
        could finish, which is the textbook definition of an interrupted
        / incomplete run.

        Also migrates any pre-existing rows with the transitional
        ``stopped`` status to ``incomplete`` so the legacy bucket is
        emptied and dashboards/filters only have to look at one value.
        """
        reason = "orphaned: agentbox process restarted before run finished"
        with self.engine.begin() as conn:
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


class SessionStore(
    PromptVersionsMixin,
    AgentVersionsMixin,
    AgentSyncMixin,
    AgentConfigEventsMixin,
    AgentToolGrantsMixin,
    SharedResourcesMixin,
    ResourcesMixin,
    ResourceBindingsMixin,
    WorkenvTemplatesMixin,
    WorkspacesMixin,
    EnvDocsMixin,
    McpOverridesMixin,
    RuntimePermissionsMixin,
    McpDiscoveryMixin,
    HostEnvMixin,
    # System mixins retired in plan 092 — SystemService now owns this domain.
    # HostEnvCallLogMixin, ProjectConfigMixin, ApiTokensMixin removed.
    # RunnerProfilesMixin removed — EngineService (091) owns this domain.
    _CoreStore,
):
    """Public store façade. Composes core CRUD + analytics + agent versions + prompt versions + shared resources + runner profiles + sync."""
