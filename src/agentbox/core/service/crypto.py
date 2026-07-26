"""Symmetric encryption for secrets at rest (Fernet).

One place to derive the encryption key, used by the ``managed_credentials``
secret store. The key is resolved from
*outside* the database it protects:

1. ``AGENTBOX_SECRET_KEY`` — a real Fernet key, or any string (hashed to
   one). Preferred: injected from env / a secret mount.
2. Fallback — a ``master.key`` file under ``creds_dir`` created ``0600``.

The key is **never** persisted into the SQLite DB. Storing the key next
to the ciphertext it unlocks makes encryption-at-rest cosmetic; a keyfile
(or env) keeps the two separable so copying the DB alone leaks nothing.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet

from agentbox.core.config import SETTINGS


def _derive_key() -> bytes:
    env_val = SETTINGS.secret_key
    if env_val:
        try:
            Fernet(env_val.encode())  # already a valid Fernet key?
            return env_val.encode()
        except Exception:
            # Arbitrary passphrase → deterministic 32-byte urlsafe key.
            digest = hashlib.sha256(env_val.encode()).digest()
            return base64.urlsafe_b64encode(digest)

    key_path = SETTINGS.creds_dir / "master.key"
    if key_path.exists():
        return key_path.read_bytes().strip()

    # No key anywhere → mint one and persist to a 0600 file OUTSIDE the DB.
    key_path.parent.mkdir(parents=True, exist_ok=True)
    new_key = Fernet.generate_key()
    key_path.write_bytes(new_key)
    key_path.chmod(0o600)
    return new_key


def fernet() -> Fernet:
    """Return a Fernet keyed from env or the out-of-DB keyfile."""
    return Fernet(_derive_key())


def encrypt(secret: str) -> str:
    return fernet().encrypt(secret.encode()).decode()


def decrypt(token: str) -> str:
    """Decrypt a token. Raises ``cryptography.fernet.InvalidToken`` on failure."""
    return fernet().decrypt(token.encode()).decode()
