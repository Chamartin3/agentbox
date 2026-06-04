"""Credential method registry."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from agentbox.core.engines.credentials.methods import Method
from agentbox.core.engines.credentials.state import CredentialState


@dataclass
class CredentialMethod:
    backend: str
    label: str
    detect: Callable[[], CredentialState]
    methods: list[Method] = field(default_factory=list)


_registry: dict[str, CredentialMethod] = {}


def register(cm: CredentialMethod) -> None:
    _registry[cm.backend] = cm


def get(backend: str) -> CredentialMethod | None:
    return _registry.get(backend)


def list_all() -> list[CredentialMethod]:
    return sorted(_registry.values(), key=lambda cm: cm.backend)


def clear() -> None:
    _registry.clear()


_CREDS_BASE = Path(os.environ.get("AGENTBOX_CREDS_DIR", "/agentbox/creds"))


def _detect_oauth(container_path: str) -> CredentialState:
    creds_file = Path(container_path)
    if creds_file.exists() and creds_file.stat().st_size > 0:
        try:
            data = json.loads(creds_file.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data:
                return CredentialState.PRESENT
        except (json.JSONDecodeError, OSError):
            return CredentialState.INVALID
    return CredentialState.MISSING


def _detect_env_var(env_var: str) -> CredentialState:
    value = os.environ.get(env_var)
    if value and len(value) > 8:
        return CredentialState.PRESENT
    if value:
        return CredentialState.INVALID
    return CredentialState.MISSING


def detect_file(path: str) -> CredentialState:
    p = Path(path)
    if not p.exists():
        return CredentialState.MISSING
    if p.stat().st_size == 0:
        return CredentialState.INVALID
    return CredentialState.PRESENT
