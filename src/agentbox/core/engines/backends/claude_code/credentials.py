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

_CREDS_BASE = SETTINGS.creds_dir


def _detect_claude() -> CredentialState:
    oauth_path = _CREDS_BASE / "claude" / "credentials.json"
    if oauth_path.exists():
        return _detect_oauth(str(oauth_path))
    home_path = Path(os.path.expanduser("~/.claude/credentials.json"))
    if home_path.exists():
        return _detect_oauth(str(home_path))
    return CredentialState.MISSING


register(
    CredentialMethod(
        backend=BackendName.CLAUDE_CODE,
        label="Claude Code",
        detect=_detect_claude,
        methods=[
            Method(
                key="import_host",
                label="Import host ~/.claude/credentials.json",
                available_on_host=True,
                host_source="~/.claude/credentials.json",
                container_target=str(_CREDS_BASE / "claude" / "credentials.json"),
            ),
            Method(
                key="login",
                label="Run `claude /login` interactively",
                command=["claude", "/login"],
            ),
        ],
    )
)
