"""Secret encryption key derivation — from env, else an out-of-DB keyfile.

The key must never land in the SQLite DB it protects; when no env key is set
it is written to a 0600 ``master.key`` under creds_dir instead.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from agentbox.core.service import crypto


def test_roundtrip_with_env_key() -> None:
    token = crypto.encrypt("hunter2")
    assert token != "hunter2"
    assert crypto.decrypt(token) == "hunter2"


def test_keyfile_fallback_is_0600_and_out_of_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    creds = tmp_path / "creds"
    monkeypatch.delenv("AGENTBOX_SECRET_KEY", raising=False)
    monkeypatch.setenv("AGENTBOX_CREDS_DIR", str(creds))

    token = crypto.encrypt("s3cr3t")
    assert crypto.decrypt(token) == "s3cr3t"

    key_file = creds / "master.key"
    assert key_file.exists(), "key must persist to a file, not the DB"
    mode = stat.S_IMODE(key_file.stat().st_mode)
    assert mode == 0o600, f"key file must be 0600, got {oct(mode)}"
