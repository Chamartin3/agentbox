"""WorkspaceHostEnvGrantManager — host env grant CRUD."""
from __future__ import annotations

import uuid
from typing import cast

from agentbox.core.data.rows import HostEnvProfileRow, WorkspaceHostEnvGrantRow
from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.workspaces.host_env_grant import WorkspaceHostEnvGrant
from agentbox.core.db.schema import host_env_profiles, workspace_host_env_grants
from agentbox.core.db.utils import now_iso


class WorkspaceHostEnvGrantManager(Manager[WorkspaceHostEnvGrant]):
    """Manager for the ``workspace_host_env_grants`` table."""

    model = WorkspaceHostEnvGrant

    # ── pure-DB primitives for host env profiles ────────────────────────

    def list_profiles(self) -> list[HostEnvProfileRow]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                host_env_profiles.select().order_by(host_env_profiles.c.name)
            )
            return [cast(HostEnvProfileRow, dict(r._mapping)) for r in rows]

    def get_profile(self, profile_id: str) -> HostEnvProfileRow | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                host_env_profiles.select().where(host_env_profiles.c.id == profile_id)
            ).first()
            return cast(HostEnvProfileRow, dict(row._mapping)) if row else None

    def upsert_profile(
        self,
        *,
        name: str,
        grants: dict,
        description: str | None = None,
        actor: str | None = None,
        profile_id: str | None = None,
    ) -> HostEnvProfileRow:
        now = now_iso()
        with self._engine.begin() as conn:
            if profile_id:
                conn.execute(
                    host_env_profiles.update()
                    .where(host_env_profiles.c.id == profile_id)
                    .values(name=name, description=description, grants=grants)
                )
            else:
                profile_id = uuid.uuid4().hex
                conn.execute(
                    host_env_profiles.insert().values(
                        id=profile_id,
                        name=name,
                        description=description,
                        grants=grants,
                        created_at=now,
                        created_by=actor,
                    )
                )
        result = self.get_profile(profile_id)
        assert result is not None
        return result

    def delete_profile(self, profile_id: str) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                host_env_profiles.delete().where(host_env_profiles.c.id == profile_id)
            )

    # ── pure-DB primitives for workspace grants ─────────────────────────

    def get_grant(self, workspace_id: str) -> WorkspaceHostEnvGrantRow | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                workspace_host_env_grants.select().where(
                    workspace_host_env_grants.c.workspace_id == workspace_id
                )
            ).first()
            return cast(WorkspaceHostEnvGrantRow, dict(row._mapping)) if row else None

    def set_grant(
        self,
        workspace_id: str,
        *,
        profile_id: str | None,
        overrides: dict | None,
        changelog: str,
        actor: str | None = None,
    ) -> WorkspaceHostEnvGrantRow:
        now = now_iso()
        with self._engine.begin() as conn:
            existing = conn.execute(
                workspace_host_env_grants.select().where(
                    workspace_host_env_grants.c.workspace_id == workspace_id
                )
            ).first()
            if existing:
                conn.execute(
                    workspace_host_env_grants.update()
                    .where(workspace_host_env_grants.c.workspace_id == workspace_id)
                    .values(
                        profile_id=profile_id,
                        overrides=overrides,
                        changelog=changelog,
                        created_at=now,
                        created_by=actor,
                    )
                )
            else:
                conn.execute(
                    workspace_host_env_grants.insert().values(
                        workspace_id=workspace_id,
                        profile_id=profile_id,
                        overrides=overrides,
                        changelog=changelog,
                        created_at=now,
                        created_by=actor,
                    )
                )
        result = self.get_grant(workspace_id)
        assert result is not None
        return result
