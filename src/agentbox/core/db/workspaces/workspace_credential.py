"""WorkspaceCredential model + manager — which credentials a workspace enables.

Maps to the ``workspace_credentials`` table. A row's existence means the
credential id is enabled for that workspace; deleting the row disables it.
The workspace owns *availability* (enable/disable); the actual secret lives
in ``managed_credentials`` or the file/env credential sources.
"""
from __future__ import annotations

from typing import Optional

from sqlmodel import Field

from agentbox.core.data._util import now_iso
from agentbox.core.db.base.manager import Manager
from agentbox.core.db.base.model import Entity
from agentbox.core.db.base.tablename import tablename


class WorkspaceCredential(Entity, table=True):
    """One enabled credential for a workspace (composite PK)."""

    __tablename__ = tablename("workspace_credentials")

    workspace_id: str = Field(primary_key=True)
    credential_id: str = Field(primary_key=True)
    created_at: str = Field(nullable=False)
    created_by: Optional[str] = Field(default=None)


workspace_credentials = WorkspaceCredential.__table__


class WorkspaceCredentialManager(Manager[WorkspaceCredential]):
    """Manager for the ``workspace_credentials`` table."""

    model = WorkspaceCredential

    def list_enabled(self, workspace_id: str) -> list[str]:
        """Credential ids enabled for a workspace (sorted)."""
        with self._engine.connect() as conn:
            rows = conn.execute(
                workspace_credentials.select().where(
                    workspace_credentials.c.workspace_id == workspace_id
                )
            ).all()
        return sorted(r._mapping["credential_id"] for r in rows)

    def set_enabled(
        self, workspace_id: str, credential_ids: list[str], *, actor: str | None = None
    ) -> list[str]:
        """Replace the enabled set for a workspace. Returns the new set."""
        now = now_iso()
        wanted = sorted(set(credential_ids))
        with self._engine.begin() as conn:
            conn.execute(
                workspace_credentials.delete().where(
                    workspace_credentials.c.workspace_id == workspace_id
                )
            )
            for cid in wanted:
                conn.execute(
                    workspace_credentials.insert().values(
                        workspace_id=workspace_id,
                        credential_id=cid,
                        created_at=now,
                        created_by=actor,
                    )
                )
        return wanted

    def delete_for_workspace(self, workspace_id: str) -> None:
        """Remove all enablements for a workspace (on workspace delete)."""
        with self._engine.begin() as conn:
            conn.execute(
                workspace_credentials.delete().where(
                    workspace_credentials.c.workspace_id == workspace_id
                )
            )
