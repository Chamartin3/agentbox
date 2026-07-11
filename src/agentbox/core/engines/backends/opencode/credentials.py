"""OpenCode backend credential registration."""

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


def _detect_opencode() -> CredentialState:
    oauth_path = _CREDS_BASE / "opencode" / "auth.json"
    if oauth_path.exists():
        return _detect_oauth(str(oauth_path))
    home_path = Path(os.path.expanduser("~/.local/share/opencode/auth.json"))
    if home_path.exists():
        return _detect_oauth(str(home_path))
    return CredentialState.MISSING


register(
    CredentialMethod(
        backend=BackendName.OPENCODE,
        label="OpenCode",
        detect=_detect_opencode,
        methods=[
            Method(
                key="import_host",
                label="Import host ~/.local/share/opencode/auth.json",
                available_on_host=True,
                host_source="~/.local/share/opencode/auth.json",
                container_target=str(_CREDS_BASE / "opencode" / "auth.json"),
            ),
            Method(
                key="login",
                label="Run `opencode login` interactively",
                command=["opencode", "login"],
            ),
        ],
    )
)
