"""Claude Code backend credential registration."""

from __future__ import annotations

import os
from pathlib import Path

from agentbox.core.config import SETTINGS
from agentbox.core.data.constants import BackendName
from agentbox.core.engines.credentials.methods import Method
from agentbox.core.engines.credentials.registry import (
    CredentialMethod,
    CredentialState,
    _detect_oauth,
    register,
)

# ── Credential locations (no magic strings scattered through the logic) ──────
CREDS_SUBDIR = "claude"  # per-backend dir under the creds volume + host ~/.claude
CRED_FILENAME = ".credentials.json"  # the claude CLI's canonical dotfile
LEGACY_CRED_FILENAME = "credentials.json"  # tolerated older no-dot name
HOST_CLAUDE_DIR = Path("~/.claude")  # unexpanded; ~ resolved at read time
# Env vars the claude CLI can authenticate with when there's no OAuth file.
AUTH_ENV_VARS = ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN")

_CREDS_BASE = SETTINGS.creds_dir
_CLAUDE_DIR = _CREDS_BASE / CREDS_SUBDIR
_CANONICAL_TARGET = _CLAUDE_DIR / CRED_FILENAME
_HOST_SOURCE = HOST_CLAUDE_DIR / CRED_FILENAME


def _claude_cred_candidates() -> list[Path]:
    # Check the canonical dotfile and the legacy no-dot name, in the creds
    # volume and in the host ~/.claude.
    home = Path(os.path.expanduser(str(HOST_CLAUDE_DIR)))
    names = (CRED_FILENAME, LEGACY_CRED_FILENAME)
    return [directory / name for directory in (_CLAUDE_DIR, home) for name in names]


def _detect_claude() -> CredentialState:
    for path in _claude_cred_candidates():
        if path.exists():
            return _detect_oauth(str(path))
    # The claude CLI also authenticates via an API key / OAuth token env var —
    # count it so a key-only setup doesn't read as "missing" when it runs fine.
    if any(os.environ.get(var) for var in AUTH_ENV_VARS):
        return CredentialState.PRESENT
    return CredentialState.MISSING


register(
    CredentialMethod(
        backend=BackendName.CLAUDE_CODE,
        label="Claude Code",
        detect=_detect_claude,
        methods=[
            Method(
                key="import_host",
                label=f"Import host {_HOST_SOURCE}",
                available_on_host=True,
                host_source=str(_HOST_SOURCE),
                container_target=str(_CANONICAL_TARGET),
            ),
            Method(
                key="login",
                label="Run `claude /login` interactively",
                command=["claude", "/login"],
            ),
        ],
    )
)
