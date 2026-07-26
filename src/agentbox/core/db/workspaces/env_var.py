"""WorkspaceEnvVar model + manager — per-workspace custom shell environment variables.

Maps to the ``workspace_env_vars`` table. Each row is a ``KEY=VALUE``
pair that is injected into the agent subprocess at run time.

These are **not** encrypted — they are plaintext workspace config, not
a secrets vault. Provider API keys should be configured via Credentials,
not env vars (credential values win over same-named workspace vars at
merge time).
"""
from __future__ import annotations

from collections.abc import Mapping

from sqlmodel import Field

from agentbox.core.data._util import now_iso
from agentbox.core.db.base.manager import Manager
from agentbox.core.db.base.model import Entity
from agentbox.core.db.base.tablename import tablename


class WorkspaceEnvVar(Entity, table=True):
    """One shell environment variable for a workspace (composite PK)."""

    __tablename__ = tablename("workspace_env_vars")

    workspace_id: str = Field(primary_key=True)
    key: str = Field(primary_key=True)
    value: str = Field(nullable=False)
    updated_at: str = Field(nullable=False)


workspace_env_vars = WorkspaceEnvVar.__table__


class WorkspaceEnvVarManager(Manager[WorkspaceEnvVar]):
    """Manager for the ``workspace_env_vars`` table."""

    model = WorkspaceEnvVar

    def list_for_workspace(self, workspace_id: str) -> dict[str, str]:
        """Return ``{KEY: VALUE}`` for a workspace (sorted by key)."""
        with self._engine.connect() as conn:
            rows = conn.execute(
                workspace_env_vars.select()
                .where(workspace_env_vars.c.workspace_id == workspace_id)
                .order_by(workspace_env_vars.c.key)
            ).all()
        return {r._mapping["key"]: r._mapping["value"] for r in rows}

    def replace_for_workspace(
        self, workspace_id: str, pairs: Mapping[str, str]
    ) -> dict[str, str]:
        """Replace the full env-var set for a workspace (atomic delete+insert).

        Returns the new ``{KEY: VALUE}`` mapping (sorted).
        """
        now = now_iso()
        with self._engine.begin() as conn:
            conn.execute(
                workspace_env_vars.delete().where(
                    workspace_env_vars.c.workspace_id == workspace_id
                )
            )
            for key, value in sorted(pairs.items()):
                conn.execute(
                    workspace_env_vars.insert().values(
                        workspace_id=workspace_id,
                        key=key,
                        value=value,
                        updated_at=now,
                    )
                )
        return dict(sorted(pairs.items()))

    def delete_for_workspace(self, workspace_id: str) -> None:
        """Remove all env-var entries for a workspace (on workspace delete)."""
        with self._engine.begin() as conn:
            conn.execute(
                workspace_env_vars.delete().where(
                    workspace_env_vars.c.workspace_id == workspace_id
                )
            )
