"""Unit tests for core/credentials/ module: registry, detection, methods."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from agentbox.core.credentials import (
    CredentialMethod,
    CredentialState,
    Method,
    clear,
    get,
    list_all,
    register,
)
from agentbox.core.credentials.methods import _upsert_env_line
from agentbox.core.credentials.registry import _detect_env_var, _detect_oauth, detect_file


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    """Clear the global registry before each test."""
    clear()
    yield
    clear()


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


def test_register_and_get() -> None:
    cm = CredentialMethod(
        backend="test_backend",
        label="Test Backend",
        detect=lambda: CredentialState.MISSING,
        methods=[Method(key="login", label="Test login")],
    )
    register(cm)

    assert get("test_backend") is cm
    assert len(list_all()) == 1
    assert list_all()[0].backend == "test_backend"


def test_list_all_returns_sorted() -> None:
    for name in ("zzz", "aaa", "mmm"):
        register(
            CredentialMethod(
                backend=name,
                label=name,
                detect=lambda: CredentialState.MISSING,
                methods=[],
            )
        )

    items = list_all()
    assert [i.backend for i in items] == ["aaa", "mmm", "zzz"]


def test_get_unknown_returns_none() -> None:
    assert get("nonexistent") is None


def test_clear_removes_all() -> None:
    register(
        CredentialMethod(
            backend="test",
            label="Test",
            detect=lambda: CredentialState.MISSING,
            methods=[],
        )
    )
    assert len(list_all()) == 1
    clear()
    assert len(list_all()) == 0


# ---------------------------------------------------------------------------
# State enum
# ---------------------------------------------------------------------------


def test_state_is_string_enum() -> None:
    assert CredentialState.MISSING.value == "missing"
    assert CredentialState.PRESENT.value == "present"
    assert CredentialState.INVALID.value == "invalid"


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------


def test_detect_file_missing(tmp_path: Path) -> None:
    p = tmp_path / "nonexistent"
    assert detect_file(str(p)) == CredentialState.MISSING


def test_detect_file_present(tmp_path: Path) -> None:
    p = tmp_path / "test.txt"
    p.write_text("hello")
    assert detect_file(str(p)) == CredentialState.PRESENT


def test_detect_file_invalid_empty(tmp_path: Path) -> None:
    p = tmp_path / "empty.txt"
    p.write_text("")
    assert detect_file(str(p)) == CredentialState.INVALID


def test_detect_oauth_present(tmp_path: Path) -> None:
    p = tmp_path / "creds.json"
    p.write_text(json.dumps({"access_token": "test"}))
    assert _detect_oauth(str(p)) == CredentialState.PRESENT


def test_detect_oauth_invalid(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text("not json")
    assert _detect_oauth(str(p)) == CredentialState.INVALID


def test_detect_oauth_missing(tmp_path: Path) -> None:
    assert _detect_oauth(str(tmp_path / "nope.json")) == CredentialState.MISSING


def test_detect_env_var_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_API_KEY", "sk-test1234567890")
    assert _detect_env_var("TEST_API_KEY") == CredentialState.PRESENT


def test_detect_env_var_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TEST_API_KEY", raising=False)
    assert _detect_env_var("TEST_API_KEY") == CredentialState.MISSING


def test_detect_env_var_invalid_short(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_API_KEY", "short")
    assert _detect_env_var("TEST_API_KEY") == CredentialState.INVALID


# ---------------------------------------------------------------------------
# Env file upsert
# ---------------------------------------------------------------------------


def test_upsert_env_line_new_key(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    _upsert_env_line(env_path, "MY_KEY", "my-value")
    content = env_path.read_text(encoding="utf-8")
    assert 'MY_KEY="my-value"' in content


def test_upsert_env_line_updates_existing(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text('MY_KEY="old-value"\nOTHER_KEY="other"\n', encoding="utf-8")
    _upsert_env_line(env_path, "MY_KEY", "new-value")
    content = env_path.read_text(encoding="utf-8")
    assert 'MY_KEY="new-value"' in content
    assert 'OTHER_KEY="other"' in content
    # Should not duplicate
    assert content.count("MY_KEY=") == 1


def test_upsert_env_line_creates_dir(tmp_path: Path) -> None:
    env_path = tmp_path / "subdir" / ".env"
    _upsert_env_line(env_path, "KEY", "val")
    assert env_path.exists()
    assert 'KEY="val"' in env_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Method apply: env_file / paste_key
# ---------------------------------------------------------------------------


def test_method_apply_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_path = tmp_path / ".env"
    method = Method(
        key="env_file",
        label="Set MY_KEY",
        env_var="MY_KEY",
    )
    # Simulate user input by pre-setting env var
    monkeypatch.setenv("MY_KEY", "test-api-key-123")

    import getpass
    original_getpass = getpass.getpass
    getpass.getpass = lambda prompt="": os.environ.get("MY_KEY", "")

    try:
        method.apply({"env_file": str(env_path)})
        content = env_path.read_text(encoding="utf-8")
        assert 'MY_KEY="test-api-key-123"' in content
    finally:
        getpass.getpass = original_getpass


def test_method_apply_host_import(tmp_path: Path) -> None:
    src = tmp_path / "source.json"
    src.write_text(json.dumps({"token": "abc"}))
    dest = tmp_path / "dest.json"

    method = Method(
        key="import_host",
        label="Import host",
        host_source=str(src),
        container_target=str(dest),
    )
    method.apply({})
    assert dest.exists()
    assert json.loads(dest.read_text(encoding="utf-8")) == {"token": "abc"}


def test_method_apply_host_import_missing_source(tmp_path: Path) -> None:
    method = Method(
        key="import_host",
        label="Import host",
        host_source=str(tmp_path / "nope.json"),
        container_target=str(tmp_path / "dest.json"),
    )
    with pytest.raises(FileNotFoundError):
        method.apply({})


# ---------------------------------------------------------------------------
# CredentialMethod detect integration
# ---------------------------------------------------------------------------


def test_credential_method_detect_called() -> None:
    called = []

    cm = CredentialMethod(
        backend="test",
        label="Test",
        detect=lambda: called.append(1) or CredentialState.PRESENT,
        methods=[],
    )
    register(cm)
    assert cm.detect() == CredentialState.PRESENT
    assert len(called) == 1
