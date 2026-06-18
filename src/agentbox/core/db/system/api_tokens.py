"""API tokens mixin — per-environment encrypted secrets.

Each token is `(environment, name)` unique. The secret is Fernet-encrypted
at rest with a key derived from the ``AGENTBOX_SECRET_KEY`` env var. If
``AGENTBOX_SECRET_KEY`` is unset, a per-DB key is generated lazily and
stored in the ``settings`` table under section ``secrets``. This is
*acceptable for single-host deployments* — production multi-host setups
should set ``AGENTBOX_SECRET_KEY`` explicitly.

The plaintext secret is **only** returned at create/rotate time. List
endpoints return the last four characters for identification.
"""

from __future__ import annotations

import warnings

import base64
import hashlib
import uuid

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.engine import Engine

from agentbox.core.config import SETTINGS
from agentbox.core.db.utils import now_iso
from agentbox.core.db.schema import api_tokens


def _key_from_env_or_db(store) -> bytes:
    """Return a Fernet key. Prefers ``AGENTBOX_SECRET_KEY``; falls back to
    a per-DB key persisted under settings(secrets, fernet_key).
    """
    env_val = SETTINGS.secret_key
    if env_val:
        # Accept either a raw Fernet key or any string we can hash to 32 bytes.
        try:
            Fernet(env_val.encode())
            return env_val.encode()
        except (ValueError, Exception):
            digest = hashlib.sha256(env_val.encode()).digest()
            return base64.urlsafe_b64encode(digest)

    existing = store.get_setting("secrets", "fernet_key")
    if existing:
        return existing.encode() if isinstance(existing, str) else existing
    new_key = Fernet.generate_key()
    store.set_setting("secrets", "fernet_key", new_key.decode(), author="system")
    return new_key


class ApiTokensMixin:
    """CRUD for the ``api_tokens`` table."""

    engine: Engine

    def _fernet(self) -> Fernet:
        return Fernet(_key_from_env_or_db(self))

    def list_api_tokens(self, *, environment: str | None = None) -> list[dict]:
        warnings.warn(
            "ApiTokensMixin.list_api_tokens is deprecated; use db.api_tokens manager instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        with self.engine.connect() as conn:
            q = api_tokens.select()
            if environment is not None:
                q = q.where(api_tokens.c.environment == environment)
            q = q.order_by(api_tokens.c.created_at.desc())
            rows = conn.execute(q)
            return [
                {
                    "id": r._mapping["id"],
                    "environment": r._mapping["environment"],
                    "name": r._mapping["name"],
                    "last_four": r._mapping["last_four"],
                    "created_at": r._mapping["created_at"],
                    "updated_at": r._mapping["updated_at"],
                }
                for r in rows
            ]

    def create_api_token(self, *, environment: str, name: str, secret: str) -> dict:
        warnings.warn(
            "ApiTokensMixin.create_api_token is deprecated; use db.api_tokens manager instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        if len(secret) < 4:
            raise ValueError("secret must be at least 4 characters")
        token_id = uuid.uuid4().hex
        ts = now_iso()
        encrypted = self._fernet().encrypt(secret.encode()).decode()
        last_four = secret[-4:]
        with self.engine.begin() as conn:
            conn.execute(
                api_tokens.insert().values(
                    id=token_id,
                    environment=environment,
                    name=name,
                    secret_encrypted=encrypted,
                    last_four=last_four,
                    created_at=ts,
                    updated_at=ts,
                )
            )
        return {
            "id": token_id,
            "environment": environment,
            "name": name,
            "last_four": last_four,
            "created_at": ts,
            "updated_at": ts,
            "secret": secret,  # only returned at create time
        }

    def rename_api_token(self, token_id: str, name: str) -> dict | None:
        warnings.warn(
            "ApiTokensMixin.rename_api_token is deprecated; use db.api_tokens manager instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        ts = now_iso()
        with self.engine.begin() as conn:
            res = conn.execute(
                api_tokens.update()
                .where(api_tokens.c.id == token_id)
                .values(name=name, updated_at=ts)
            )
            if res.rowcount == 0:
                return None
            row = conn.execute(
                api_tokens.select().where(api_tokens.c.id == token_id)
            ).first()
        assert row is not None
        m = row._mapping
        return {
            "id": m["id"],
            "environment": m["environment"],
            "name": m["name"],
            "last_four": m["last_four"],
            "created_at": m["created_at"],
            "updated_at": m["updated_at"],
        }

    def rotate_api_token(self, token_id: str, *, secret: str) -> dict | None:
        warnings.warn(
            "ApiTokensMixin.rotate_api_token is deprecated; use db.api_tokens manager instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        if len(secret) < 4:
            raise ValueError("secret must be at least 4 characters")
        ts = now_iso()
        encrypted = self._fernet().encrypt(secret.encode()).decode()
        last_four = secret[-4:]
        with self.engine.begin() as conn:
            res = conn.execute(
                api_tokens.update()
                .where(api_tokens.c.id == token_id)
                .values(
                    secret_encrypted=encrypted,
                    last_four=last_four,
                    updated_at=ts,
                )
            )
            if res.rowcount == 0:
                return None
            row = conn.execute(
                api_tokens.select().where(api_tokens.c.id == token_id)
            ).first()
        assert row is not None
        m = row._mapping
        return {
            "id": m["id"],
            "environment": m["environment"],
            "name": m["name"],
            "last_four": m["last_four"],
            "created_at": m["created_at"],
            "updated_at": m["updated_at"],
            "secret": secret,
        }

    def delete_api_token(self, token_id: str) -> bool:
        with self.engine.begin() as conn:
            res = conn.execute(api_tokens.delete().where(api_tokens.c.id == token_id))
            return res.rowcount > 0

    def reveal_api_token(self, token_id: str) -> str | None:
        """Decrypt and return the plaintext secret. Use with extreme care.

        Intended for the runtime path that injects the token into a runner
        profile's environment, *not* for API responses.
        """
        warnings.warn(
            "ApiTokensMixin.reveal_api_token is deprecated; use db.api_tokens manager instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        with self.engine.connect() as conn:
            row = conn.execute(
                api_tokens.select().where(api_tokens.c.id == token_id)
            ).first()
            if row is None:
                return None
            try:
                return (
                    self._fernet()
                    .decrypt(row._mapping["secret_encrypted"].encode())
                    .decode()
                )
            except InvalidToken:
                return None
