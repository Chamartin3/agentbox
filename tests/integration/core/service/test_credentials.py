"""CredentialService — inventory, add/delete, workspace enablement, materialization.

The security contract under test: secrets go in and are materialized into a
run's env, but are never returned to a caller; enablement is per-workspace and
validated; materialization decrypts only the enabled set.
"""

from __future__ import annotations

import pytest

from agentbox.core.service.credentials import CredentialService


def test_inventory_merges_registry_and_db_sources() -> None:
    svc = CredentialService()
    base = svc.inventory()
    # Registry always contributes provider/backend entries (env/file sources).
    assert base, "registry should contribute credential entries"
    assert all(e["source"] in {"env", "file", "db"} for e in base)
    # A UI-added credential shows up tagged source=db.
    svc.add_credential(
        credential_id="my.key", label="My Key", kind="api_key",
        env_var="MY_API_KEY", secret="sk-secret-1234",
    )
    entry = {e["id"]: e for e in svc.inventory()}["my.key"]
    assert entry["source"] == "db"
    assert entry["kind"] == "api_key"
    assert entry["env_var"] == "MY_API_KEY"
    assert entry["state"] == "present"


def test_add_credential_is_write_only_no_secret_leaks() -> None:
    svc = CredentialService()
    row = svc.add_credential(
        credential_id="w.only", label="WO", kind="api_key",
        env_var="WO_KEY", secret="sk-supersecret-9876",
    )
    # Public row carries last_four for identification, never the value.
    assert row["last_four"] == "9876"
    assert "secret" not in row
    assert "secret_encrypted" not in row


def test_add_api_key_requires_env_var() -> None:
    svc = CredentialService()
    with pytest.raises(ValueError, match="env_var"):
        svc.add_credential(
            credential_id="bad", label="Bad", kind="api_key",
            env_var=None, secret="x",
        )


def test_set_workspace_credentials_rejects_unknown_id() -> None:
    svc = CredentialService()
    with pytest.raises(ValueError, match="unknown credential ids"):
        svc.set_workspace_credentials("ws1", ["does.not.exist"])


def test_resolve_env_decrypts_only_enabled_managed_creds() -> None:
    svc = CredentialService()
    svc.add_credential(
        credential_id="ws.openai", label="OpenAI", kind="api_key",
        env_var="OPENAI_API_KEY", secret="sk-openai-abcd",
    )
    svc.add_credential(
        credential_id="ws.other", label="Other", kind="api_key",
        env_var="OTHER_KEY", secret="sk-other-zzzz",
    )
    # Enable only one for the workspace.
    svc.set_workspace_credentials("wsA", ["ws.openai"])
    env = svc.resolve_env_for_workspace("wsA")
    assert env == {"OPENAI_API_KEY": "sk-openai-abcd"}  # decrypt round-trip, only enabled


def test_resolve_env_empty_when_nothing_enabled() -> None:
    svc = CredentialService()
    assert svc.resolve_env_for_workspace("unconfigured-ws") == {}


def test_delete_credential_removes_it() -> None:
    svc = CredentialService()
    svc.add_credential(
        credential_id="gone", label="Gone", kind="api_key",
        env_var="GONE_KEY", secret="sk-gone-1111",
    )
    assert svc.delete_credential("gone") is True
    assert "gone" not in {e["id"] for e in svc.inventory()}
    assert svc.delete_credential("gone") is False  # idempotent-ish: already gone


def test_no_reveal_path_on_system_service() -> None:
    # The extraction path was removed; nothing exposes a stored secret value.
    from agentbox.core.service.system import SystemService

    assert not hasattr(SystemService, "reveal_api_token")
