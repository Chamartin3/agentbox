"""Credential method registry."""

from __future__ import annotations

import importlib
import json
import os
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from pathlib import Path
from typing import Callable

from agentbox.core.config import SETTINGS
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


_loaded = False


def _credential_modules() -> list[str]:
    """Sibling ``.credentials`` module of every ``agentbox.backends`` entry
    point, plus the providers key table. Modules that don't exist are
    tolerated by ``load_all``."""
    mods: list[str] = []
    for ep in entry_points(group="agentbox.backends"):
        pkg = ep.value.split(":", 1)[0]
        mods.append(f"{pkg}.credentials")
    mods.append("agentbox.core.engines.providers.credentials")
    return mods


def load_all(*, force: bool = False) -> None:
    """Import every credential-registration module so its ``register()``
    side effects populate the registry. Idempotent: repeated calls are a
    no-op unless ``force`` is set (which reloads already-imported modules —
    used by tests that ``clear()`` the registry between cases)."""
    global _loaded
    if _loaded and not force:
        return
    for name in _credential_modules():
        try:
            mod = importlib.import_module(name)
        except ModuleNotFoundError:
            continue
        if force:
            importlib.reload(mod)
    _loaded = True


_CREDS_BASE = SETTINGS.creds_dir


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
