"""ApiTokenManager — API credential token CRUD."""
from __future__ import annotations

from typing import cast

from sqlalchemy import Executable, select as sa_select, update as sa_update, delete as sa_delete
from sqlalchemy.engine import Row

from agentbox.core.data.rows import ApiTokenPublicRow, ApiTokenRow
from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.system.api_token import ApiToken


class ApiTokenManager(Manager[ApiToken]):
    """Manager for the ``api_tokens`` table."""

    model = ApiToken

    # ------------------------------------------------------------------
    # Domain-specific operations (pure DB — no business logic)
    # ------------------------------------------------------------------

    def list_tokens(
        self, *, environment: str | None = None
    ) -> list[ApiTokenRow]:
        """Return all tokens, optionally filtered by environment (dicts)."""
        stmt = sa_select(ApiToken.__table__)
        if environment is not None:
            stmt = stmt.where(ApiToken.__table__.c.environment == environment)
        stmt = stmt.order_by(ApiToken.__table__.c.created_at.desc())
        rows = self._list_raw(stmt)
        return [cast(ApiTokenRow, dict(r)) for r in rows]

    def insert_token(
        self,
        *,
        token_id: str,
        environment: str,
        name: str,
        secret_encrypted: str,
        last_four: str,
        created_at: str,
        updated_at: str,
    ) -> ApiTokenPublicRow:
        """Insert a new API token row. Returns the public view (no secret)."""
        tbl = ApiToken.__table__
        with self._engine.begin() as conn:
            conn.execute(
                tbl.insert().values(
                    id=token_id,
                    environment=environment,
                    name=name,
                    secret_encrypted=secret_encrypted,
                    last_four=last_four,
                    created_at=created_at,
                    updated_at=updated_at,
                )
            )
        return ApiTokenPublicRow(
            id=token_id,
            environment=environment,
            name=name,
            last_four=last_four,
            created_at=created_at,
            updated_at=updated_at,
        )

    def get_token(self, token_id: str) -> ApiTokenRow | None:
        """Fetch a single token row by id. Returns typed row or None."""
        tbl = ApiToken.__table__
        row = self._one_raw(
            sa_select(tbl).where(tbl.c.id == token_id)
        )
        return cast(ApiTokenRow, dict(row)) if row is not None else None

    def update_token_name(
        self, token_id: str, name: str, updated_at: str
    ) -> ApiTokenRow | None:
        """Rename a token. Returns updated row, or None if not found."""
        tbl = ApiToken.__table__
        with self._engine.begin() as conn:
            res = conn.execute(
                sa_update(tbl)
                .where(tbl.c.id == token_id)
                .values(name=name, updated_at=updated_at)
            )
            if res.rowcount == 0:
                return None
            row = conn.execute(
                sa_select(tbl).where(tbl.c.id == token_id)
            ).first()
        return cast(ApiTokenRow, dict(row._mapping)) if row is not None else None

    def update_token_secret(
        self,
        token_id: str,
        secret_encrypted: str,
        last_four: str,
        updated_at: str,
    ) -> ApiTokenRow | None:
        """Rotate a token's secret. Returns updated row, or None if not found."""
        tbl = ApiToken.__table__
        with self._engine.begin() as conn:
            res = conn.execute(
                sa_update(tbl)
                .where(tbl.c.id == token_id)
                .values(
                    secret_encrypted=secret_encrypted,
                    last_four=last_four,
                    updated_at=updated_at,
                )
            )
            if res.rowcount == 0:
                return None
            row = conn.execute(
                sa_select(tbl).where(tbl.c.id == token_id)
            ).first()
        return cast(ApiTokenRow, dict(row._mapping)) if row is not None else None

    def delete_token(self, token_id: str) -> bool:
        """Delete a token by id. Returns True if a row was deleted."""
        tbl = ApiToken.__table__
        with self._engine.begin() as conn:
            res = conn.execute(
                sa_delete(tbl).where(tbl.c.id == token_id)
            )
            return res.rowcount > 0

    def get_token_secret_encrypted(self, token_id: str) -> str | None:
        """Fetch just the encrypted secret for a token. Returns None if not found."""
        tbl = ApiToken.__table__
        row = self._one_raw(
            sa_select(tbl.c.secret_encrypted).where(tbl.c.id == token_id)
        )
        if row is None:
            return None
        return row[0] if row else None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _one_raw(self, stmt: Executable) -> Row | None:
        """Execute a statement and return a single Row, or None."""
        with self._engine.connect() as conn:
            row = conn.execute(stmt).first()
        return row

    def _list_raw(self, stmt: Executable) -> list:
        """Execute a statement and return a list of Row objects."""
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).all()
        return [r._mapping for r in rows]
