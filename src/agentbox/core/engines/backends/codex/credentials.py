"""Codex CLI backend credential registration."""

from __future__ import annotations

import os
from pathlib import Path

from agentbox.core.data.constants import BackendName
from agentbox.core.engines.credentials.methods import Method
from agentbox.core.engines.credentials.registry import (
    CredentialMethod,
    CredentialState,
    _detect_oauth,
    register,
)


def _detect_codex() -> CredentialState:
    config_path = Path(os.path.expanduser("~/.config/codex/credentials.json"))
    if config_path.exists():
        return _detect_oauth(str(config_path))
    if os.environ.get("CODEX_API_KEY"):
        return CredentialState.PRESENT
    return CredentialState.MISSING


register(
    CredentialMethod(
        backend=BackendName.CODEX,
        label="Codex CLI",
        detect=_detect_codex,
        methods=[
            Method(
                key="login",
                label="Run `codex login` interactively",
                command=["codex", "login"],
            ),
        ],
    )
)
