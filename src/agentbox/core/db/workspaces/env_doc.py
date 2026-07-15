"""Workspace env-doc models and managers — environment documentation for workspaces.

Maps to the ``workspace_env_docs`` and ``workspace_env_doc_versions`` tables.
"""
from __future__ import annotations

import uuid
from typing import Optional, cast

from sqlalchemy import JSON, func, select
from sqlmodel import Field, Index, UniqueConstraint

from agentbox.core.db.base.model import Entity
from agentbox.core.db.base.manager import Manager
from agentbox.core.db.base.tablename import tablename, tableargs
from agentbox.core.db.schema import workspace_env_doc_versions, workspace_env_docs
from agentbox.core.data._util import now_iso
from agentbox.core.data.rows import EnvDocRow, WorkspaceEnvDocPointerRow


class WorkspaceEnvDoc(Entity, table=True):
    """Points to the active env-doc version for a workspace."""

    __tablename__ = tablename("workspace_env_docs")

    workspace_id: str = Field(primary_key=True)
    active_version_id: Optional[str] = Field(
        foreign_key="workspace_env_doc_versions.id", ondelete="SET NULL", default=None,
    )


class WorkspaceEnvDocVersion(Entity, table=True):
    """A versioned environment documentation snapshot for a workspace."""

    __tablename__ = tablename("workspace_env_doc_versions")

    id: str = Field(primary_key=True)
    workspace_id: str = Field(nullable=False)
    version_number: int = Field(nullable=False)
    content_json: dict = Field(nullable=False, sa_type=JSON)
    is_draft: int = Field(nullable=False, default=0)
    changelog: str = Field(nullable=False)
    created_at: str = Field(nullable=False)
    created_by: Optional[str] = Field(default=None)

    __table_args__ = tableargs(
        UniqueConstraint("workspace_id", "version_number", name="uq_workspace_env_doc_version"),
        Index("ix_workspace_env_doc_versions_workspace_id", "workspace_id"),
    )


class WorkspaceEnvDocManager(Manager[WorkspaceEnvDoc]):
    """Manager for the ``workspace_env_docs`` table (active-version pointer)."""

    model = WorkspaceEnvDoc

    def get_pointer(self, workspace_id: str) -> WorkspaceEnvDocPointerRow | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                workspace_env_docs.select().where(
                    workspace_env_docs.c.workspace_id == workspace_id
                )
            ).first()
            return cast(WorkspaceEnvDocPointerRow, dict(row._mapping)) if row else None


class WorkspaceEnvDocVersionManager(Manager[WorkspaceEnvDocVersion]):
    """Manager for the ``workspace_env_doc_versions`` table."""

    model = WorkspaceEnvDocVersion

    # ── pure-DB primitives (ported from EnvDocsMixin) ───────────────────

    def get_active(self, workspace_id: str) -> EnvDocRow | None:
        with self._engine.connect() as conn:
            ptr = conn.execute(
                workspace_env_docs.select().where(
                    workspace_env_docs.c.workspace_id == workspace_id
                )
            ).first()
            if not ptr or not ptr.active_version_id:
                return None
            ver = conn.execute(
                workspace_env_doc_versions.select().where(
                    workspace_env_doc_versions.c.id == ptr.active_version_id
                )
            ).first()
            return cast(EnvDocRow, dict(ver._mapping)) if ver else None

    def list_for_workspace(self, workspace_id: str) -> list[EnvDocRow]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                workspace_env_doc_versions.select()
                .where(workspace_env_doc_versions.c.workspace_id == workspace_id)
                .order_by(workspace_env_doc_versions.c.version_number.desc())
            )
            return [cast(EnvDocRow, dict(r._mapping)) for r in rows]

    def get_by_version_id(self, version_id: str) -> EnvDocRow | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                workspace_env_doc_versions.select().where(
                    workspace_env_doc_versions.c.id == version_id
                )
            ).first()
            return cast(EnvDocRow, dict(row._mapping)) if row else None

    def next_version_number(self, workspace_id: str) -> int:
        with self._engine.connect() as conn:
            return conn.execute(
                select(
                    func.coalesce(
                        func.max(workspace_env_doc_versions.c.version_number), 0
                    )
                    + 1
                ).where(workspace_env_doc_versions.c.workspace_id == workspace_id)
            ).scalar_one()

    def save(
        self,
        workspace_id: str,
        content: dict,
        *,
        changelog: str,
        publish: bool = True,
        actor: str | None = None,
    ) -> EnvDocRow:
        version_id = uuid.uuid4().hex
        next_num = self.next_version_number(workspace_id)
        now = now_iso()
        with self._engine.begin() as conn:
            conn.execute(
                workspace_env_doc_versions.insert().values(
                    id=version_id,
                    workspace_id=workspace_id,
                    version_number=next_num,
                    content_json=content,
                    is_draft=0 if publish else 1,
                    changelog=changelog,
                    created_at=now,
                    created_by=actor,
                )
            )
            ptr_exists = conn.execute(
                workspace_env_docs.select().where(
                    workspace_env_docs.c.workspace_id == workspace_id
                )
            ).first()
            if publish:
                if ptr_exists:
                    conn.execute(
                        workspace_env_docs.update()
                        .where(workspace_env_docs.c.workspace_id == workspace_id)
                        .values(active_version_id=version_id)
                    )
                else:
                    conn.execute(
                        workspace_env_docs.insert().values(
                            workspace_id=workspace_id, active_version_id=version_id
                        )
                    )
            elif not ptr_exists:
                conn.execute(
                    workspace_env_docs.insert().values(
                        workspace_id=workspace_id, active_version_id=None
                    )
                )
        result = self.get_by_version_id(version_id)
        assert result is not None
        return result

    def publish(
        self,
        workspace_id: str,
        version_id: str,
    ) -> EnvDocRow:
        with self._engine.begin() as conn:
            ver = conn.execute(
                workspace_env_doc_versions.select().where(
                    (workspace_env_doc_versions.c.id == version_id)
                    & (workspace_env_doc_versions.c.workspace_id == workspace_id)
                )
            ).first()
            if not ver:
                raise ValueError(
                    f"env doc version {version_id!r} not found for workspace"
                )
            conn.execute(
                workspace_env_doc_versions.update()
                .where(workspace_env_doc_versions.c.id == version_id)
                .values(is_draft=0)
            )
            ptr = conn.execute(
                workspace_env_docs.select().where(
                    workspace_env_docs.c.workspace_id == workspace_id
                )
            ).first()
            if ptr:
                conn.execute(
                    workspace_env_docs.update()
                    .where(workspace_env_docs.c.workspace_id == workspace_id)
                    .values(active_version_id=version_id)
                )
            else:
                conn.execute(
                    workspace_env_docs.insert().values(
                        workspace_id=workspace_id, active_version_id=version_id
                    )
                )
        result = self.get_by_version_id(version_id)
        assert result is not None
        return result
