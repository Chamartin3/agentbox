"""SQLite-backed store for runs, sessions, transcripts, and usage.

Uses SQLAlchemy Core for schema + queries. We stay on Core (not the ORM)
because the data shapes are flat rows, the public API returns plain
dicts / dataclasses, and the analytics queries are conditional aggregates
that read more clearly as SQL expressions than as ORM relationships.

``SessionStore`` is composed from:
- ``_CoreStore``  — connection mgmt + sessions/runs/usage/guardrails CRUD
- ``AgentToolGrantsMixin`` — agent-scoped tool grant/revoke CRUD
- ``AnalyticsMixin``       — read-only rollups and time-series
- ``PromptVersionsMixin``  — draft/publish/rollback for prompt history
"""

from __future__ import annotations

import contextlib
import logging
import uuid
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine

from agentbox.core.constants import RunStatus
from agentbox.core.data.agent_config_events import AgentConfigEventsMixin
from agentbox.core.data.agent_sync import AgentSyncMixin
from agentbox.core.data.agent_tool_grants import AgentToolGrantsMixin
from agentbox.core.data.agent_versions import AgentVersionsMixin
from agentbox.core.data.analytics import AnalyticsMixin
from agentbox.core.data.api_tokens import ApiTokensMixin
from agentbox.core.data.env_docs import EnvDocsMixin
from agentbox.core.data.host_env import HostEnvMixin
from agentbox.core.data.mcp_discovery import McpDiscoveryMixin
from agentbox.core.data.mcp_overrides import McpOverridesMixin
from agentbox.core.data.project_config import ProjectConfigMixin
from agentbox.core.data.prompts import PromptVersionsMixin
from agentbox.core.data.records import RunRecord, now_iso, row_to_run
from agentbox.core.data.resource_bindings import ResourceBindingsMixin
from agentbox.core.data.resources import ResourcesMixin
from agentbox.core.data.runner_profiles import RunnerProfilesMixin
from agentbox.core.data.runtime_permissions import RuntimePermissionsMixin
from agentbox.core.data.schema import (
    guardrail_results,
    metadata,
    run_comments,
    run_prompts,
    runs,
    sessions,
    usage,
    webhook_deliveries,
)
from agentbox.core.data.settings import SettingsMixin
from agentbox.core.data.shared_resources import SharedResourcesMixin
from agentbox.core.data.workspaces import WorkspacesMixin

logger = logging.getLogger(__name__)


class _CoreStore:
    """Connection + CRUD for sessions, runs, usage, guardrails, run_prompts."""

    def __init__(self, db_path: Path):
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
        self._migrate()
        self.engine.dispose()
        self._reap_orphaned_runs()

    def _run_alembic_migrations(self) -> None:
        """Run pending Alembic migrations on startup."""
        import logging

        logger = logging.getLogger(__name__)

        try:
            from alembic import command
            from alembic.config import Config

            alembic_cfg = Config()
            alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{self.db_path}")

            # Find the migrations directory — check a few candidate paths so
            # both editable installs and built wheels work.
            import agentbox

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

    def _migrate(self) -> None:
        """Add columns introduced after the initial schema was deployed."""
        _add_column_if_missing = [
            ("runs", "validation_status", "TEXT"),
            ("runs", "validation_errors", "TEXT"),
            ("runs", "schema_validated_via", "TEXT"),
            ("runs", "post_status", "TEXT"),
            ("runs", "post_errors", "TEXT"),
            ("runs", "conversation_format", "TEXT"),
            ("runs", "conversation_uri", "TEXT"),
            ("runs", "runner_profile_id", "TEXT"),
            ("runs", "resource_snapshot", "TEXT"),
            ("runs", "mcp_snapshot", "TEXT"),
            ("runs", "runner_snapshot", "TEXT"),
            ("prompt_versions", "content_hash", "TEXT"),
            ("agent_meta", "deleted_at", "TEXT"),
            ("runner_profiles", "output_mode", "TEXT NOT NULL DEFAULT 'auto'"),
            ("agent_versions", "resolved_tool_grants", "TEXT"),
            ("host_env_call_log", "surface", "TEXT DEFAULT 'host_env'"),
        ]
        with self.engine.begin() as conn:
            for table, col, col_type in _add_column_if_missing:
                existing = [
                    row[1]
                    for row in conn.exec_driver_sql(
                        f"PRAGMA table_info({table})"
                    ).fetchall()
                ]
                if col not in existing:
                    conn.exec_driver_sql(
                        f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"
                    )

            # Create runner_profiles table if missing
            try:
                conn.exec_driver_sql(
                    """CREATE TABLE IF NOT EXISTS runner_profiles (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        description TEXT,
                        backend TEXT NOT NULL,
                        provider TEXT,
                        model TEXT,
                        timeout_seconds INTEGER,
                        base_url TEXT,
                        api_key_env TEXT,
                        output_mode TEXT NOT NULL DEFAULT 'auto',
                        params_json TEXT NOT NULL DEFAULT '{}',
                        headers_json TEXT NOT NULL DEFAULT '{}',
                        extra_args_json TEXT NOT NULL DEFAULT '[]',
                        is_enabled INTEGER NOT NULL DEFAULT 1,
                        is_system_default INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        CHECK(is_enabled IN (0, 1)),
                        CHECK(is_system_default IN (0, 1))
                    )"""
                )
                # Create indexes
                conn.exec_driver_sql(
                    "CREATE INDEX IF NOT EXISTS idx_runner_profiles_backend_provider "
                    "ON runner_profiles(backend, provider)"
                )
                conn.exec_driver_sql(
                    "CREATE INDEX IF NOT EXISTS idx_runner_profiles_enabled "
                    "ON runner_profiles(is_enabled)"
                )
            except Exception:
                pass

            # Create agent_runner_profiles table if missing
            with contextlib.suppress(Exception):
                conn.exec_driver_sql(
                    """CREATE TABLE IF NOT EXISTS agent_runner_profiles (
                        agent_id TEXT PRIMARY KEY,
                        runner_profile_id TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        FOREIGN KEY(runner_profile_id) REFERENCES runner_profiles(id)
                    )"""
                )

            # Extend resources.type CHECK constraint to include schema/script
            try:
                row = conn.exec_driver_sql(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name='resources'"
                ).fetchone()
                if row and row[0] and "'schema'" not in row[0]:
                    new_sql = row[0].replace(
                        "type IN ('document', 'folder', 'skill')",
                        "type IN ('document', 'folder', 'skill', 'schema', 'script')",
                    )
                    if new_sql != row[0]:
                        conn.exec_driver_sql("PRAGMA writable_schema=ON")
                        conn.exec_driver_sql(
                            "UPDATE sqlite_master SET sql=? "
                            "WHERE type='table' AND name='resources'",
                            (new_sql,),
                        )
                        cur_ver = conn.exec_driver_sql(
                            "PRAGMA schema_version"
                        ).fetchone()[0]
                        conn.exec_driver_sql(f"PRAGMA schema_version={cur_ver + 1}")
                        conn.exec_driver_sql("PRAGMA writable_schema=OFF")
            except Exception:
                logger.exception("migrate: failed to extend resources_type_check")

            # Create index on runs.runner_profile_id
            with contextlib.suppress(Exception):
                conn.exec_driver_sql(
                    "CREATE INDEX IF NOT EXISTS idx_runs_runner_profile_id "
                    "ON runs(runner_profile_id)"
                )

            # Create agents table if missing (needed for FK references)
            with contextlib.suppress(Exception):
                conn.exec_driver_sql(
                    """CREATE TABLE IF NOT EXISTS agents (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )"""
                )

            # Create agent_tool_grants table if missing
            with contextlib.suppress(Exception):
                conn.exec_driver_sql(
                    """CREATE TABLE IF NOT EXISTS agent_tool_grants (
                        id TEXT PRIMARY KEY,
                        agent_id TEXT NOT NULL
                            REFERENCES agents(id) ON DELETE CASCADE,
                        tool_name TEXT NOT NULL,
                        changelog TEXT NOT NULL,
                        granted_at TEXT NOT NULL,
                        granted_by TEXT,
                        revoked_at TEXT,
                        revoked_by TEXT,
                        revoke_changelog TEXT,
                        UNIQUE(agent_id, tool_name)
                    )"""
                )
                conn.exec_driver_sql(
                    "CREATE INDEX IF NOT EXISTS ix_agent_tool_grants_agent "
                    "ON agent_tool_grants(agent_id)"
                )

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

    # ----- sessions ---------------------------------------------------------

    def create_session(self, agent_id: str, mode: str, workdir: str | None) -> str:
        sid = uuid.uuid4().hex
        with self.engine.begin() as conn:
            conn.execute(
                sessions.insert().values(
                    id=sid,
                    agent_id=agent_id,
                    mode=mode,
                    workdir=workdir,
                    created_at=now_iso(),
                )
            )
        return sid

    def touch_session(self, session_id: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                sessions.update()
                .where(sessions.c.id == session_id)
                .values(last_used_at=now_iso())
            )

    def get_session(self, session_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                sessions.select().where(sessions.c.id == session_id)
            ).first()
            return dict(row._mapping) if row else None

    def set_session_workdir(self, session_id: str, workdir: str) -> None:
        """Update a session's workdir. Used by the executor on first run."""
        with self.engine.begin() as conn:
            conn.execute(
                sessions.update()
                .where(sessions.c.id == session_id)
                .values(workdir=workdir)
            )

    # ----- runs -------------------------------------------------------------

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
        """Mark a run terminal. Idempotent on already-terminal rows.

        The executor's finally-block and the external /complete endpoint
        can both call this; whoever gets there first wins. The other's
        call becomes a no-op so we don't overwrite a real output/error
        with the wrapper's empty result.
        """
        import json as _json

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
        """Persist conversation metadata for a run."""
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
        """Record the consumer's post-processor outcome for this run.

        Called via ``POST /api/runs/{run_id}/post_outcome`` after the
        consumer's webhook handler has applied (or failed) its side-effects.
        Does not modify the run's primary ``status`` — that is the executor's
        own result. The ``post_status`` column is the consumer's verdict.
        """
        import json as _json

        values: dict = {"post_status": "ok" if ok else "fail"}
        if errors is not None:
            values["post_errors"] = _json.dumps(
                {"error_kind": error_kind, "errors": errors}
            )
        with self.engine.begin() as conn:
            conn.execute(runs.update().where(runs.c.id == run_id).values(**values))

    def list_orphaned_unnotified_runs(self) -> list[RunRecord]:
        """Return orphan-reaped runs that never had their webhook fired.

        An orphan is any terminal row whose ``error`` was set by the
        reaper (contains the literal "orphaned"). ``post_status`` is the
        column the webhook delivery path stamps after a successful send,
        so ``post_status IS NULL`` identifies runs that the post pipeline
        never got to. Used by the API startup hook to fire webhooks for
        runs whose executor task died before the finally block.
        """
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
        """Mark any rows still in ``running`` state as ``incomplete``.

        Called on process startup. Any row left in ``running`` past a
        restart belongs to a dead executor task — its ``finally`` block
        never reached ``finish_run``, so the row would otherwise stay
        orphaned forever (hiding from terminal-status filters and
        skewing activity rollups). The agent didn't fail to do its
        task; the executor process died before completion — that's an
        interrupted run, i.e. ``incomplete``.
        """
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
        """Update only the status column. Used for post-terminal transitions
        like flipping ``ok`` ↔ ``failed`` based on webhook delivery."""
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

    # ----- run comments ----------------------------------------------------

    def add_run_comment(self, run_id: str, author: str, body: str) -> dict:
        with self.engine.begin() as conn:
            result = conn.execute(
                run_comments.insert().values(
                    run_id=run_id,
                    author=author,
                    body=body,
                    created_at=now_iso(),
                )
            )
            new_id = result.inserted_primary_key[0]
            row = conn.execute(
                run_comments.select().where(run_comments.c.id == new_id)
            ).first()
        return dict(row._mapping) if row else {}

    def list_run_comments(self, run_id: str) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                run_comments.select()
                .where(run_comments.c.run_id == run_id)
                .order_by(run_comments.c.created_at)
            )
            return [dict(r._mapping) for r in rows]

    # ----- usage / guardrails ----------------------------------------------

    def record_usage(self, run_id: str, payload: dict) -> None:
        values = {
            "run_id": run_id,
            "model": payload.get("model"),
            "input_tokens": payload.get("input_tokens", 0),
            "output_tokens": payload.get("output_tokens", 0),
            "cache_read_tokens": payload.get("cache_read_tokens", 0),
            "cache_write_tokens": payload.get("cache_write_tokens", 0),
            "cost_usd": payload.get("cost_usd"),
        }
        stmt = sqlite_insert(usage).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[usage.c.run_id],
            set_={
                "model": func.coalesce(stmt.excluded.model, usage.c.model),
                "input_tokens": usage.c.input_tokens + stmt.excluded.input_tokens,
                "output_tokens": usage.c.output_tokens + stmt.excluded.output_tokens,
                "cache_read_tokens": usage.c.cache_read_tokens
                + stmt.excluded.cache_read_tokens,
                "cache_write_tokens": usage.c.cache_write_tokens
                + stmt.excluded.cache_write_tokens,
                "cost_usd": func.coalesce(usage.c.cost_usd, 0)
                + func.coalesce(stmt.excluded.cost_usd, 0),
            },
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)

    def get_usage(self, run_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(usage.select().where(usage.c.run_id == run_id)).first()
            return dict(row._mapping) if row else None

    def record_guardrail(
        self, run_id: str, name: str, ok: bool, message: str | None, attempt: int
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                guardrail_results.insert().values(
                    run_id=run_id,
                    name=name,
                    ok=int(ok),
                    message=message,
                    attempt=attempt,
                    created_at=now_iso(),
                )
            )

    def list_guardrails(self, run_id: str) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                guardrail_results.select()
                .where(guardrail_results.c.run_id == run_id)
                .order_by(guardrail_results.c.id)
            )
            return [dict(r._mapping) for r in rows]

    # ----- webhook deliveries ------------------------------------------------

    def record_webhook_delivery(
        self,
        run_id: str,
        attempt: int,
        url: str,
        payload: dict | None = None,
        response_status: int | None = None,
        response_body: str | None = None,
        latency_ms: int | None = None,
        error: str | None = None,
    ) -> None:
        import json as _json

        with self.engine.begin() as conn:
            conn.execute(
                webhook_deliveries.insert().values(
                    run_id=run_id,
                    attempt=attempt,
                    url=url,
                    payload_json=_json.dumps(payload) if payload else None,
                    response_status=response_status,
                    response_body=response_body,
                    latency_ms=latency_ms,
                    error=error,
                    ts=now_iso(),
                )
            )

    def list_webhook_deliveries(self, run_id: str) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                webhook_deliveries.select()
                .where(webhook_deliveries.c.run_id == run_id)
                .order_by(webhook_deliveries.c.id)
            )
            return [dict(r._mapping) for r in rows]

    # ----- run prompts ------------------------------------------------------

    def save_run_prompt(self, run_id: str, fragments_json: str) -> None:
        stmt = sqlite_insert(run_prompts).values(
            run_id=run_id, fragments=fragments_json, created_at=now_iso()
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[run_prompts.c.run_id],
            set_={"fragments": stmt.excluded.fragments},
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)

    def get_run_prompt(self, run_id: str) -> str | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                select(run_prompts.c.fragments).where(run_prompts.c.run_id == run_id)
            ).first()
            return row[0] if row else None

    # ----- composition snapshot -------------------------------------------

    def save_run_snapshot(
        self,
        run_id: str,
        rendered_prompt: dict,
        variables: dict,
        validation_status: str,
        validation_errors: list[str],
        composition_snapshot: dict | None = None,
    ) -> None:
        import json as _json

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
        import json as _json

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
        resource_snapshot: list[dict] | None = None,
        mcp_snapshot: dict | None = None,
    ) -> None:
        import json as _json

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
        runner_snapshot: dict,
    ) -> None:
        """Persist the runner config resolved at dispatch time.

        Append-only — write once, never updated. This is the historical
        record of what backend/model/timeout actually ran the agent.
        Mutating the bound profile or rebinding the agent must not affect
        a previously persisted snapshot.
        """
        import json as _json

        with self.engine.begin() as conn:
            conn.execute(
                runs.update()
                .where(
                    runs.c.id == run_id,
                    runs.c.runner_snapshot.is_(None),
                )
                .values(runner_snapshot=_json.dumps(runner_snapshot))
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
    WorkspacesMixin,
    EnvDocsMixin,
    McpOverridesMixin,
    RuntimePermissionsMixin,
    McpDiscoveryMixin,
    HostEnvMixin,
    RunnerProfilesMixin,
    SettingsMixin,
    ProjectConfigMixin,
    ApiTokensMixin,
    AnalyticsMixin,
    _CoreStore,
):
    """Public store façade. Composes core CRUD + analytics + agent versions + prompt versions + shared resources + runner profiles + sync."""
