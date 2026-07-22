"""ManagedCredential model + manager — credentials added through the web UI.

Maps to the ``managed_credentials`` table. Secrets are stored Fernet-encrypted
(``secret_encrypted``); the manager never returns the ciphertext through its
public list view — only presence metadata (``last_four``). Encryption/decryption
is service policy (``CredentialService``), not the manager's job.
"""
from __future__ import annotations

from typing import Optional, cast

from sqlalchemy import delete as sa_delete, select as sa_select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import Field

from agentbox.core.data.rows import ManagedCredentialPublicRow
from agentbox.core.db.base.model import Entity
from agentbox.core.db.base.manager import Manager
from agentbox.core.db.base.tablename import tablename


class ManagedCredential(Entity, table=True):
    """A credential entered through the web UI, encrypted at rest."""

    __tablename__ = tablename("managed_credentials")

    id: str = Field(primary_key=True)
    label: str = Field(nullable=False)
    kind: str = Field(nullable=False)  # "api_key" | "login"
    env_var: Optional[str] = Field(default=None)
    secret_encrypted: str = Field(nullable=False)
    last_four: str = Field(nullable=False)
    created_at: str = Field(nullable=False)
    updated_at: str = Field(nullable=False)


managed_credentials = ManagedCredential.__table__

_PUBLIC_COLS = (
    managed_credentials.c.id,
    managed_credentials.c.label,
    managed_credentials.c.kind,
    managed_credentials.c.env_var,
    managed_credentials.c.last_four,
    managed_credentials.c.created_at,
    managed_credentials.c.updated_at,
)


class ManagedCredentialManager(Manager[ManagedCredential]):
    """Manager for the ``managed_credentials`` table (pure DB, no crypto)."""

    model = ManagedCredential

    def list_public(self) -> list[ManagedCredentialPublicRow]:
        """All credentials without the secret column."""
        with self._engine.connect() as conn:
            rows = conn.execute(
                sa_select(*_PUBLIC_COLS).order_by(managed_credentials.c.id)
            ).all()
        return [cast(ManagedCredentialPublicRow, dict(r._mapping)) for r in rows]

    def get_public(self, credential_id: str) -> ManagedCredentialPublicRow | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                sa_select(*_PUBLIC_COLS).where(managed_credentials.c.id == credential_id)
            ).first()
        return cast(ManagedCredentialPublicRow, dict(row._mapping)) if row else None

    def get_secret_encrypted(self, credential_id: str) -> str | None:
        """Ciphertext for one credential (for internal materialization only)."""
        with self._engine.connect() as conn:
            row = conn.execute(
                sa_select(managed_credentials.c.secret_encrypted).where(
                    managed_credentials.c.id == credential_id
                )
            ).first()
        return row[0] if row else None

    def upsert(
        self,
        *,
        credential_id: str,
        label: str,
        kind: str,
        env_var: str | None,
        secret_encrypted: str,
        last_four: str,
        created_at: str,
        updated_at: str,
    ) -> ManagedCredentialPublicRow:
        """Insert or overwrite a credential. Returns the public view."""
        values = {
            "id": credential_id,
            "label": label,
            "kind": kind,
            "env_var": env_var,
            "secret_encrypted": secret_encrypted,
            "last_four": last_four,
            "created_at": created_at,
            "updated_at": updated_at,
        }
        stmt = sqlite_insert(managed_credentials).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[managed_credentials.c.id],
            set_={
                "label": stmt.excluded.label,
                "kind": stmt.excluded.kind,
                "env_var": stmt.excluded.env_var,
                "secret_encrypted": stmt.excluded.secret_encrypted,
                "last_four": stmt.excluded.last_four,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        with self._engine.begin() as conn:
            conn.execute(stmt)
        result = self.get_public(credential_id)
        assert result is not None, f"credential {credential_id!r} must exist after upsert"
        return result

    def delete_by_id(self, credential_id: str) -> bool:
        """Delete a credential. Returns True if a row was removed."""
        with self._engine.begin() as conn:
            res = conn.execute(
                sa_delete(managed_credentials).where(managed_credentials.c.id == credential_id)
            )
            return res.rowcount > 0
