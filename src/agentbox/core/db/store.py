"""SQLite-backed store for runs, sessions, transcripts, and usage.

Uses SQLAlchemy Core for schema + queries. We stay on Core (not the ORM)
because the data shapes are flat rows, the public API returns plain
dicts / dataclasses, and the analytics queries are conditional aggregates
that read more clearly as SQL expressions than as ORM relationships.

``SessionStore`` is composed from per-domain mixins managed by dedicated
services (ResourceService, ExecutionService, etc.). Legacy CRUD mixins
(SessionsMixin, RunsMixin, etc.) have been retired in favour of these
service-layer abstractions.
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
# Execution mixins retired in plan 088 — ExecutionService now owns the run lifecycle.
# Resource mixins retired in plan 090_01 — ResourceService now owns the resource domain.
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

    # ------------------------------------------------------------------
    # Resource-domain backward-compat redirects → ResourceService
    # ------------------------------------------------------------------
    def _rsvc(self):
        from agentbox.core.service.resources.service import ResourceService  # noqa: PLC0415
        return ResourceService()

    def get_repo_resource(self, resource_id: str):
        return self._rsvc()._resources.get_resource(resource_id)

    def get_repo_resource_by_slug(self, slug: str):
        return self._rsvc()._resources.get_by_slug(slug)

    def list_repo_resources(self, *, type: str | None = None, query: str | None = None, include_deleted: bool = False, limit: int = 50, offset: int = 0):
        return self._rsvc()._resources.list_resources(type=type, query=query, include_deleted=include_deleted, limit=limit, offset=offset)

    def count_repo_resources(self, *, type: str | None = None, query: str | None = None, include_deleted: bool = False):
        return self._rsvc()._resources.count_resources(type=type, query=query, include_deleted=include_deleted)

    def create_repo_resource(self, slug: str, type: str, display_name: str, *, description: str | None = None, tags: list[str] | None = None, created_by: str | None = None):
        return self._rsvc()._resources.create_resource(slug=slug, type=type, display_name=display_name, description=description, tags=tags, created_by=created_by)

    def update_repo_resource(self, resource_id: str, *, type: str | None = None, display_name: str | None = None, description: str | None = None, tags: list[str] | None = None):
        return self._rsvc()._resources.update_resource(resource_id, type=type, display_name=display_name, description=description, tags=tags)

    def soft_delete_repo_resource(self, resource_id: str, *, reason: str = "deleted via SessionStore"):
        self._rsvc()._resources.soft_delete(resource_id, reason=reason)

    def get_repo_version(self, version_id: str):
        return self._rsvc()._resource_versions.get_version(version_id)

    def list_repo_versions(self, resource_id: str):
        return self._rsvc()._resource_versions.list_versions(resource_id)

    def get_active_repo_version(self, resource_id: str):
        return self._rsvc()._resource_versions.get_active_version(resource_id)

    def publish_repo_version(self, version_id: str, *, reason: str, activated_by: str | None = None):
        return self._rsvc()._resource_versions.publish_version(version_id, reason=reason, activated_by=activated_by)

    def rollback_repo_resource(self, resource_id: str, target_version: int, *, reason: str, activated_by: str | None = None):
        return self._rsvc()._resource_versions.rollback_resource(resource_id, target_version, reason=reason, activated_by=activated_by)

    def import_repo_version(self, resource_id: str, blobs, *, import_source: str, changelog: str, source_metadata: dict | None = None, metadata: dict | None = None, draft: bool = False, created_by: str | None = None, activate: bool = True):
        return self._rsvc()._resource_versions.import_version(resource_id, blobs, import_source=import_source, changelog=changelog, source_metadata=source_metadata, metadata=metadata, draft=draft, created_by=created_by, activate=activate)

    def read_repo_blob(self, version_id: str, relative_path: str = ""):
        return self._rsvc()._resource_blobs.get_blob(version_id, relative_path)

    def iter_repo_blobs(self, version_id: str):
        return self._rsvc()._resource_blobs.iter_blobs(version_id)

    # Shared resources (legacy names — no "shared_" prefix)
    def get_resource(self, id: str, version: int):
        return self._rsvc()._shared_resources.get_versioned(id, version)

    def get_active_resource(self, id: str):
        return self._rsvc()._shared_resources.get_active(id)

    def list_resources(self, *, kind: str | None = None, q: str | None = None, limit: int = 50, offset: int = 0):
        return self._rsvc()._shared_resources.list_active(kind=kind, q=q, limit=limit, offset=offset)

    def count_active_resources(self, *, kind: str | None = None, q: str | None = None):
        return self._rsvc()._shared_resources.count_active(kind=kind, q=q)

    def list_resource_versions(self, id: str, *, limit: int = 50, offset: int = 0):
        return self._rsvc()._shared_resources.list_versions(id, limit=limit, offset=offset)

    def create_resource(self, id: str, kind: str, name: str, *, description: str | None = None, content: str | None = None, config_json: str | None = None, author: str | None = None, changelog: str | None = None, tags: list[str] | None = None, activate: bool = True):
        return self._rsvc()._shared_resources.create(id, kind, name, description=description, content=content, config_json=config_json, author=author, changelog=changelog, tags=tags, activate=activate)

    def create_resource_version(self, id: str, *, content: str | None = None, config_json: str | None = None, author: str | None = None, changelog: str | None = None, activate: bool = False, **fields_to_update):
        return self._rsvc()._shared_resources.create_version(id, content=content, config_json=config_json, author=author, changelog=changelog, activate=activate, **fields_to_update)

    def activate_resource(self, id: str, version: int):
        return self._rsvc()._shared_resources.activate_version(id, version)

    # Shared resources (new names — with "shared_" prefix, for ResourceService callers)
    def get_shared_resource(self, id: str, version: int):
        return self._rsvc()._shared_resources.get_versioned(id, version)

    def get_active_shared_resource(self, id: str):
        return self._rsvc()._shared_resources.get_active(id)

    def list_shared_resources(self, *, kind: str | None = None, q: str | None = None, limit: int = 50, offset: int = 0):
        return self._rsvc()._shared_resources.list_active(kind=kind, q=q, limit=limit, offset=offset)

    def count_shared_resources(self, *, kind: str | None = None, q: str | None = None):
        return self._rsvc()._shared_resources.count_active(kind=kind, q=q)

    def list_shared_resource_versions(self, id: str, *, limit: int = 50, offset: int = 0):
        return self._rsvc()._shared_resources.list_versions(id, limit=limit, offset=offset)

    def create_shared_resource(self, id: str, kind: str, name: str, *, description: str | None = None, content: str | None = None, config_json: str | None = None, author: str | None = None, changelog: str | None = None, tags: list[str] | None = None, activate: bool = True):
        return self._rsvc()._shared_resources.create(id, kind, name, description=description, content=content, config_json=config_json, author=author, changelog=changelog, tags=tags, activate=activate)

    def create_shared_resource_version(self, id: str, *, content: str | None = None, config_json: str | None = None, author: str | None = None, changelog: str | None = None, activate: bool = False, **fields_to_update):
        return self._rsvc()._shared_resources.create_version(id, content=content, config_json=config_json, author=author, changelog=changelog, activate=activate, **fields_to_update)

    def activate_shared_resource(self, id: str, version: int):
        return self._rsvc()._shared_resources.activate_version(id, version)

    # Prompt / workspace bindings (→ ResourceService)
    def list_prompt_bindings(self, agent_id: str):
        return self._rsvc()._prompt_bindings.list_for_agent(agent_id)

    def replace_prompt_bindings(self, agent_id: str, bindings, *, reason: str, actor: str | None = None):
        return self._rsvc()._prompt_bindings.replace_for_agent(agent_id, bindings, reason=reason, actor=actor)

    def list_workspace_file_bindings(self, workspace_id: str):
        return self._rsvc()._file_bindings.list_for_workspace(workspace_id)

    def replace_workspace_file_bindings(self, workspace_id: str, bindings, *, reason: str, actor: str | None = None):
        return self._rsvc()._file_bindings.replace_for_workspace(workspace_id, bindings, reason=reason, actor=actor)

    def count_workspace_file_bindings_by_workspace(self):
        return self._rsvc()._file_bindings.count_by_workspace()

    def replace_workspace_skill_bindings(self, workspace_id: str, skill_resource_ids, *, reason: str = "skill bindings update", actor: str | None = None):
        return self._rsvc()._file_bindings.replace_skill_bindings(workspace_id, skill_resource_ids, reason=reason, actor=actor)

    def list_workspace_subagents(self, workspace_id: str):
        from agentbox.core.service.workspaces.service import WorkspaceService  # noqa: PLC0415
        return WorkspaceService()._subagents.list_for_workspace(workspace_id)

    def replace_workspace_subagents(self, workspace_id: str, subagents, *, actor: str | None = None):
        from agentbox.core.service.workspaces.service import WorkspaceService  # noqa: PLC0415
        return WorkspaceService()._subagents.replace_for_workspace(workspace_id, subagents, actor=actor)
