"""pi CLI backend credential registration."""

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


def _detect_pi() -> CredentialState:
    config_path = Path(os.path.expanduser("~/.config/pi/credentials.json"))
    if config_path.exists():
        return _detect_oauth(str(config_path))
    session_path = Path(os.path.expanduser("~/.pi/session.json"))
    if session_path.exists():
        return _detect_oauth(str(session_path))
    return CredentialState.MISSING


register(
    CredentialMethod(
        backend=BackendName.PI,
        label="pi CLI",
        detect=_detect_pi,
        methods=[
            Method(
                key="login",
                label="Run `pi login` interactively",
                command=["pi", "login"],
            ),
        ],
    )
)
