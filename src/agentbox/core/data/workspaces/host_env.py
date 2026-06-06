"""Host-env profile + workspace grant CRUD (Plan 06)."""

from __future__ import annotations

import uuid

from sqlalchemy.engine import Engine

from agentbox.core.data.records import now_iso
from agentbox.core.data.schema import (
    host_env_profiles,
    workspace_host_env_grants,
)


def _validate_changelog(s: str) -> str:
    if not s or len(s.strip()) < 3:
        raise ValueError("changelog must be at least 3 characters")
    return s.strip()


class HostEnvMixin:
    engine: Engine

    # --- profiles ---

    def list_host_env_profiles(self) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                host_env_profiles.select().order_by(host_env_profiles.c.name)
            )
            return [dict(r._mapping) for r in rows]

    def get_host_env_profile(self, profile_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                host_env_profiles.select().where(host_env_profiles.c.id == profile_id)
            ).first()
            return dict(row._mapping) if row else None

    def upsert_host_env_profile(
        self,
        *,
        name: str,
        grants: dict,
        description: str | None = None,
        actor: str | None = None,
        profile_id: str | None = None,
    ) -> dict:
        now = now_iso()
        with self.engine.begin() as conn:
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
        out = self.get_host_env_profile(profile_id)
        assert out is not None
        return out

    def delete_host_env_profile(self, profile_id: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                host_env_profiles.delete().where(host_env_profiles.c.id == profile_id)
            )

    # --- workspace grants ---

    def get_workspace_host_env(self, workspace_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                workspace_host_env_grants.select().where(
                    workspace_host_env_grants.c.workspace_id == workspace_id
                )
            ).first()
            return dict(row._mapping) if row else None

    def set_workspace_host_env(
        self,
        workspace_id: str,
        *,
        profile_id: str | None,
        overrides: dict | None,
        changelog: str,
        actor: str | None = None,
    ) -> dict:
        changelog = _validate_changelog(changelog)
        now = now_iso()
        with self.engine.begin() as conn:
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
        row = self.get_workspace_host_env(workspace_id)
        assert row is not None
        return row

    def resolve_workspace_host_env(self, workspace_id: str) -> dict:
        from agentbox.core.workspaces.permissions import resolve_grants
        row = self.get_workspace_host_env(workspace_id)
        if not row:
            return {"grants": resolve_grants(None, None), "profile_id": None}
        profile = (
            self.get_host_env_profile(row["profile_id"])
            if row.get("profile_id")
            else None
        )
        grants = resolve_grants(
            profile["grants"] if profile else None, row.get("overrides")
        )
        return {
            "grants": grants,
            "profile_id": row.get("profile_id"),
            "overrides": row.get("overrides"),
        }
