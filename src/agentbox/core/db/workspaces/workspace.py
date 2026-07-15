"""Workspace model and manager — workspace registry.

Maps to the ``workspaces`` table. The canonical registry of workspaces
known to agentbox.
"""
from __future__ import annotations

from typing import Optional, cast

from sqlalchemy import delete as sa_delete, text
from sqlmodel import CheckConstraint, Field

from agentbox.core.db.base.model import Entity
from agentbox.core.db.base.manager import Manager
from agentbox.core.db.base.tablename import tablename, tableargs
from agentbox.core.db.resources.binding import WorkspaceFileResourceBinding
from agentbox.core.db.schema import workspaces as workspaces_schema
from agentbox.core.data._util import now_iso
from agentbox.core.data.rows import WorkspaceRow


class Workspace(Entity, table=True):
    """A named workspace — the unit of organisational grouping in agentbox."""

    __tablename__ = tablename("workspaces")

    name: str = Field(primary_key=True)
    description: Optional[str] = Field(default=None)
    path: Optional[str] = Field(default=None)
    source: str = Field(nullable=False, default="db", sa_column_kwargs={"server_default": "db"})
    created_at: str = Field(nullable=False)
    created_by: Optional[str] = Field(default=None)
    updated_at: str = Field(nullable=False)

    __table_args__ = tableargs(
        CheckConstraint("source IN ('manifest', 'db')", name="workspaces_source_check"),
    )


_SATELLITE_TABLES: tuple[str, ...] = (
    "workspace_subagents",
    "workspace_mcp_overrides",
    "workspace_mcp_tool_overrides",
    "workspace_mcp_policies",
    "workspace_env_docs",
    "workspace_env_doc_versions",
    "workspace_file_resource_bindings",
    "workspace_runtime_permissions",
)


class WorkspaceManager(Manager[Workspace]):
    """Manager for the ``workspaces`` table with cascade delete support."""

    model = Workspace

    # ── pure-DB primitives (ported from WorkspacesMixin) ─────────────────

    def list_all(self) -> list[WorkspaceRow]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                workspaces_schema.select().order_by(workspaces_schema.c.name)
            )
            return [cast(WorkspaceRow, dict(r._mapping)) for r in rows]

    def get_by_name(self, name: str) -> WorkspaceRow | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                workspaces_schema.select().where(workspaces_schema.c.name == name)
            ).first()
            return cast(WorkspaceRow, dict(row._mapping)) if row else None

    def insert(
        self,
        name: str,
        *,
        description: str | None = None,
        path: str | None = None,
        source: str = "db",
        actor: str | None = None,
    ) -> WorkspaceRow:
        now = now_iso()
        with self._engine.begin() as conn:
            existing = conn.execute(
                workspaces_schema.select().where(workspaces_schema.c.name == name)
            ).first()
            if existing:
                raise ValueError(f"workspace {name!r} already exists")
            conn.execute(
                workspaces_schema.insert().values(
                    name=name,
                    description=description,
                    path=path,
                    source=source,
                    created_at=now,
                    created_by=actor,
                    updated_at=now,
                )
            )
        result = self.get_by_name(name)
        assert result is not None
        return result

    def upsert(
        self,
        name: str,
        *,
        description: str | None = None,
        path: str | None = None,
        source: str | None = None,
        actor: str | None = None,
    ) -> WorkspaceRow:
        now = now_iso()
        with self._engine.begin() as conn:
            existing = conn.execute(
                workspaces_schema.select().where(workspaces_schema.c.name == name)
            ).first()
            if existing is None:
                conn.execute(
                    workspaces_schema.insert().values(
                        name=name,
                        description=description,
                        path=path,
                        source=source or "db",
                        created_at=now,
                        created_by=actor,
                        updated_at=now,
                    )
                )
            else:
                values: dict = {"updated_at": now}
                if description is not None:
                    values["description"] = description
                if path is not None:
                    values["path"] = path
                if source is not None:
                    values["source"] = source
                conn.execute(
                    workspaces_schema.update()
                    .where(workspaces_schema.c.name == name)
                    .values(**values)
                )
        result = self.get_by_name(name)
        assert result is not None
        return result

    def delete_cascade(self, workspace_name: str) -> dict[str, int]:
        """Delete a workspace and all satellite records.

        Returns ``{table_name: rows_deleted}``. Idempotent — missing tables
        are skipped.
        """
        # Import here to avoid circular imports with sibling modules
        from agentbox.core.db.workspaces.env_doc import WorkspaceEnvDoc, WorkspaceEnvDocVersion  # noqa: PLC0415
        from agentbox.core.db.workspaces.mcp_override import (  # noqa: PLC0415
            WorkspaceMcpOverride,
            WorkspaceMcpPolicy,
            WorkspaceMcpToolOverride,
        )
        from agentbox.core.db.workspaces.runtime_permission import WorkspaceRuntimePermission  # noqa: PLC0415
        from agentbox.core.db.workspaces.subagent import WorkspaceSubagent  # noqa: PLC0415

        counts: dict[str, int] = {}
        cascade_tables = [
            WorkspaceEnvDocVersion.__table__,
            WorkspaceEnvDoc.__table__,
            WorkspaceMcpToolOverride.__table__,
            WorkspaceMcpOverride.__table__,
            WorkspaceMcpPolicy.__table__,
            WorkspaceSubagent.__table__,
            WorkspaceRuntimePermission.__table__,
            WorkspaceFileResourceBinding.__table__,
        ]
        with self._engine.begin() as conn:
            for table in cascade_tables:
                col = (
                    table.c.workspace_id if hasattr(table.c, "workspace_id")
                    else getattr(table.c, "name", None)
                )
                if col is None:
                    continue
                result = conn.execute(sa_delete(table).where(col == workspace_name))
                if result.rowcount:
                    counts[table.name] = result.rowcount
            result = conn.execute(
                workspaces_schema.delete().where(workspaces_schema.c.name == workspace_name)
            )
            counts["workspaces"] = result.rowcount or 0
        return counts

    def backfill_from_satellites(self) -> int:
        now = now_iso()
        inserted = 0
        with self._engine.begin() as conn:
            existing_names = {
                r[0]
                for r in conn.execute(text("SELECT name FROM workspaces")).fetchall()
            }
            seen: set[str] = set()
            for table in _SATELLITE_TABLES:
                try:
                    rows = conn.execute(
                        text(f"SELECT DISTINCT workspace_id FROM {table}")
                    ).fetchall()
                except Exception:
                    continue
                for (name,) in rows:
                    if name and name not in existing_names and name not in seen:
                        seen.add(name)
            for name in seen:
                conn.execute(
                    text(
                        "INSERT INTO workspaces (name, source, created_at, updated_at) "
                        "VALUES (:name, 'db', :now, :now)"
                    ),
                    {"name": name, "now": now},
                )
                inserted += 1
        return inserted

    def prune_phantoms(self, keep: set[str]) -> list[str]:
        deleted: list[str] = []
        with self._engine.begin() as conn:
            rows = conn.execute(text("SELECT name, source FROM workspaces")).fetchall()
            for name, source in rows:
                if name in keep:
                    continue
                if source == "manifest":
                    continue
                has_satellite = False
                for table in _SATELLITE_TABLES:
                    try:
                        r = conn.execute(
                            text(
                                f"SELECT 1 FROM {table} WHERE workspace_id = :n LIMIT 1"
                            ),
                            {"n": name},
                        ).first()
                    except Exception:
                        continue
                    if r is not None:
                        has_satellite = True
                        break
                if has_satellite:
                    continue
                conn.execute(
                    text("DELETE FROM workspaces WHERE name = :n"),
                    {"n": name},
                )
                deleted.append(name)
        return deleted
