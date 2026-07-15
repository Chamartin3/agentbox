"""HostEnvProfile model + manager — host environment capability profiles.

Maps to the ``host_env_profiles`` table. Each profile defines a set of
grants (permissions) for interacting with the host environment.
"""
from __future__ import annotations

import uuid
from typing import Optional, cast

from sqlalchemy import JSON
from sqlmodel import Field, UniqueConstraint

from agentbox.core.data._util import now_iso
from agentbox.core.data.rows import HostEnvProfileRow
from agentbox.core.db.base.model import Entity
from agentbox.core.db.base.manager import Manager
from agentbox.core.db.base.tablename import tablename, tableargs


class HostEnvProfile(Entity, table=True):
    """A named host environment profile with capability grants."""

    __tablename__ = tablename("host_env_profiles")

    id: str = Field(primary_key=True)
    name: str = Field(nullable=False)
    description: Optional[str] = Field(default=None)
    grants: str = Field(nullable=False, sa_type=JSON)
    created_at: str = Field(nullable=False)
    created_by: Optional[str] = Field(default=None)

    __table_args__ = tableargs(
        UniqueConstraint("name", name="uq_host_env_profile_name"),
    )


host_env_profiles = HostEnvProfile.__table__  # table sourced from the SQLModel entity


class HostEnvProfileManager(Manager[HostEnvProfile]):
    """Manager for the ``host_env_profiles`` table.

    Profiles are shared reusable presets referenced by agent-scoped grants.
    """

    model = HostEnvProfile

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
