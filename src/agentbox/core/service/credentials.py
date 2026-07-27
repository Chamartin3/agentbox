"""CredentialService — one system for every credential.

Unifies the three credential sources into a single inventory (files + env
via the registry, plus UI-added credentials in ``managed_credentials``),
owns per-workspace enablement, and materializes a run's credential env.

Security invariants:
- Values flow **in** (``add_credential``) and are **used** (``resolve_env_for_workspace``,
  called only by the executor) — they never flow **out**. There is no
  method that returns a stored secret to a caller.
- ``resolve_env_for_workspace`` is the single decrypt path and is internal
  to run materialization.
"""

from __future__ import annotations

import os

from cryptography.fernet import InvalidToken

from agentbox.core.data._util import now_iso
from agentbox.core.data.rows import (
    CredentialInventoryEntry,
    ManagedCredentialPublicRow,
)
from agentbox.core.engines.credentials.registry import list_all, load_all
from agentbox.core.service import crypto
from agentbox.core.service.base import Service

_VALID_KINDS = ("api_key", "login")


def _registry_env_var(cm: object) -> str | None:
    methods = getattr(cm, "methods", []) or []
    return next((m.env_var for m in methods if getattr(m, "env_var", None)), None)


class CredentialService(Service):
    """Inventory, add/delete, workspace enablement, and run materialization."""

    # ── Inventory (read; never values) ────────────────────────────────────

    def inventory(self) -> list[CredentialInventoryEntry]:
        """Every credential the system knows about, from all three sources."""
        load_all()
        out: list[CredentialInventoryEntry] = []
        for cm in list_all():
            env_var = _registry_env_var(cm)
            kind = "api_key" if env_var else "login"
            out.append(
                CredentialInventoryEntry(
                    id=cm.backend,
                    label=cm.label,
                    kind=kind,
                    source="env" if env_var else "file",
                    env_var=env_var,
                    state=cm.detect().value,
                )
            )
        for row in self._db.managed_credentials.list_public():
            out.append(
                CredentialInventoryEntry(
                    id=row["id"],
                    label=row["label"],
                    kind=row["kind"],
                    source="db",
                    env_var=row["env_var"],
                    state="present",
                )
            )
        return out

    def _inventory_ids(self) -> set[str]:
        return {e["id"] for e in self.inventory()}

    # ── Add / delete (UI-managed credentials; write-only) ─────────────────

    def add_credential(
        self,
        *,
        credential_id: str,
        label: str,
        kind: str,
        env_var: str | None,
        secret: str,
    ) -> ManagedCredentialPublicRow:
        """Encrypt and store a UI-added credential. Overwrites by id."""
        if kind not in _VALID_KINDS:
            raise ValueError(f"kind must be one of {_VALID_KINDS}")
        if kind == "api_key" and not env_var:
            raise ValueError("api_key credentials require an env_var")
        if not secret:
            raise ValueError("secret is required")
        ts = now_iso()
        return self._db.managed_credentials.upsert(
            credential_id=credential_id,
            label=label,
            kind=kind,
            env_var=env_var,
            secret_encrypted=crypto.encrypt(secret),
            last_four=secret[-4:],
            created_at=ts,
            updated_at=ts,
        )

    def delete_credential(self, credential_id: str) -> bool:
        """Delete a UI-added credential. Returns True if one was removed."""
        return self._db.managed_credentials.delete_by_id(credential_id)

    # ── Per-workspace enablement ──────────────────────────────────────────

    def list_workspace_credentials(self, workspace_id: str) -> list[str]:
        """Credential ids enabled for a workspace."""
        return self._db.workspace_credentials.list_enabled(workspace_id)

    def list_workspace_overrides(self, workspace_id: str) -> dict[str, str]:
        """credential_id → env-var-name override for a workspace."""
        return self._db.workspace_credentials.get_overrides(workspace_id)

    def set_workspace_credentials(
        self,
        workspace_id: str,
        credential_ids: list[str],
        *,
        overrides: dict[str, str] | None = None,
        actor: str | None = None,
    ) -> list[str]:
        """Replace the enabled set (+ env-var overrides). Validates ids exist."""
        known = self._inventory_ids()
        unknown = [c for c in credential_ids if c not in known]
        if unknown:
            raise ValueError(f"unknown credential ids: {unknown}")
        return self._db.workspace_credentials.set_enabled(
            workspace_id, credential_ids, overrides=overrides, actor=actor
        )

    # ── Materialization (internal decrypt; executor-only) ─────────────────

    def resolve_env_for_workspace(self, workspace_id: str) -> dict[str, str]:
        """Env vars (name→value) for the workspace's enabled api_key creds.

        The ONLY path that decrypts a stored secret. Called by the executor
        when building a run's env — never exposed over the API or CLI. Login
        (file) credentials are not env-materialized; they live on disk under
        ``creds_dir`` and are picked up by the backend CLI directly.
        """
        enabled = set(self._db.workspace_credentials.list_enabled(workspace_id))
        if not enabled:
            return {}
        # Per-workspace remap: expose a credential under a chosen env-var name.
        overrides = self._db.workspace_credentials.get_overrides(workspace_id)
        out: dict[str, str] = {}
        # Registry env credentials (provider keys): pass through from the
        # container env only when the credential is enabled for this workspace.
        load_all()
        for cm in list_all():
            if cm.backend not in enabled:
                continue
            env_var = _registry_env_var(cm)
            if env_var and os.environ.get(env_var):
                out[overrides.get(cm.backend) or env_var] = os.environ[env_var]
        # UI-added api_key credentials: decrypt.
        for row in self._db.managed_credentials.list_public():
            if row["id"] not in enabled:
                continue
            if row["kind"] != "api_key" or not row["env_var"]:
                continue
            enc = self._db.managed_credentials.get_secret_encrypted(row["id"])
            if not enc:
                continue
            try:
                out[overrides.get(row["id"]) or row["env_var"]] = crypto.decrypt(enc)
            except InvalidToken:
                continue
        return out
