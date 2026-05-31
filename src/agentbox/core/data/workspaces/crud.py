"""Workspaces registry mixin — canonical source of truth for workspaces.

Before this mixin existed, "which workspaces exist?" was answered by
unioning agentbox.toml, the workspaces/ dir, and every workspace_*
satellite table. That allowed phantom rows to linger forever and made
delete impossible without manual SQL.

This mixin owns the `workspaces` table. Satellite tables (env-docs,
MCP overrides, file bindings, host-env grants, runtime permissions,
subagents) still key by workspace_id but are conceptually children
of this registry. ``delete_workspace_cascade`` purges all of them.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

from agentbox.core.data.records import now_iso
from agentbox.core.data.row_types import WorkspaceRow
from agentbox.core.data.schema import workspaces

# Satellite tables whose rows belong to a workspace. Listed here so
# delete_workspace_cascade and the boot backfill stay in sync.
_SATELLITE_TABLES: tuple[str, ...] = (
    "workspace_subagents",
    "workspace_mcp_overrides",
    "workspace_mcp_tool_overrides",
    "workspace_mcp_policies",
    "workspace_host_env_grants",
    "workspace_env_docs",
    "workspace_env_doc_versions",
    "workspace_file_resource_bindings",
    "workspace_runtime_permissions",
)


class WorkspacesMixin:
    """CRUD + cascade-delete for the canonical workspaces registry."""

    engine: Engine

    def list_workspaces(self) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(workspaces.select().order_by(workspaces.c.name))
            return [dict(r._mapping) for r in rows]

    def get_workspace(self, name: str) -> WorkspaceRow | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                workspaces.select().where(workspaces.c.name == name)
            ).first()
            return WorkspaceRow(**dict(row._mapping)) if row else None

    def create_workspace(
        self,
        name: str,
        *,
        description: str | None = None,
        path: str | None = None,
        source: str = "db",
        actor: str | None = None,
    ) -> dict:
        if not name or not name.strip():
            raise ValueError("workspace name is required")
        if source not in ("manifest", "db"):
            raise ValueError(f"invalid source {source!r}")
        now = now_iso()
        with self.engine.begin() as conn:
            existing = conn.execute(
                workspaces.select().where(workspaces.c.name == name)
            ).first()
            if existing:
                raise ValueError(f"workspace {name!r} already exists")
            conn.execute(
                workspaces.insert().values(
                    name=name,
                    description=description,
                    path=path,
                    source=source,
                    created_at=now,
                    created_by=actor,
                    updated_at=now,
                )
            )
        out = self.get_workspace(name)
        assert out is not None
        return out

    def upsert_workspace(
        self,
        name: str,
        *,
        description: str | None = None,
        path: str | None = None,
        source: str | None = None,
        actor: str | None = None,
    ) -> dict:
        """Insert if missing, update metadata otherwise. Used by manifest sync."""
        now = now_iso()
        with self.engine.begin() as conn:
            existing = conn.execute(
                workspaces.select().where(workspaces.c.name == name)
            ).first()
            if existing is None:
                conn.execute(
                    workspaces.insert().values(
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
                    workspaces.update()
                    .where(workspaces.c.name == name)
                    .values(**values)
                )
        out = self.get_workspace(name)
        assert out is not None
        return out

    def delete_workspace_cascade(self, name: str) -> dict:
        """Delete a workspace and all rows in satellite tables.

        Returns a dict ``{table_name: rows_deleted}`` so callers can log /
        surface what was removed. Idempotent — missing tables are skipped.
        """
        counts: dict[str, int] = {}
        with self.engine.begin() as conn:
            for table in _SATELLITE_TABLES:
                try:
                    result = conn.execute(
                        text(f"DELETE FROM {table} WHERE workspace_id = :name"),
                        {"name": name},
                    )
                    if result.rowcount:
                        counts[table] = result.rowcount
                except Exception:
                    # Table may not exist in older deployments; skip.
                    continue
            result = conn.execute(workspaces.delete().where(workspaces.c.name == name))
            counts["workspaces"] = result.rowcount or 0
        return counts

    def backfill_workspaces_from_satellites(self) -> int:
        """One-shot backfill: insert any workspace_id seen in satellite
        tables that's not already in the registry.

        Safety net for state created before the registry table existed
        (the migration already does this, but new satellite rows could
        in principle be written by buggy code that bypasses the registry).
        Returns the number of rows inserted.
        """
        now = now_iso()
        inserted = 0
        with self.engine.begin() as conn:
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

    def prune_phantom_workspaces(self, keep: set[str]) -> list[str]:
        """Delete registry rows that are demonstrably phantoms.

        A phantom is a registry row that:
          - is not in ``keep`` (manifest + agent-referenced + ``default``),
          - has ``source != 'manifest'`` (manifest rows are always kept),
          - has zero rows in every satellite table.

        On-disk directories are left untouched — they may be scratch
        directories from past experiments and the user can clean them up
        manually. Returns the list of names that were deleted.
        """
        deleted: list[str] = []
        with self.engine.begin() as conn:
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
