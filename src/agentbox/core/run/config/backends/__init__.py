"""Backend-specific config generators."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import BackendConfigGenerator
from .claude_code import ClaudeCodeConfigGenerator
from .codex import CodexConfigGenerator
from .opencode import OpenCodeConfigGenerator
from .pi import PiConfigGenerator

if TYPE_CHECKING:
    from pathlib import Path

    from agentbox.core.data import AgentDef
    from agentbox.core.run.config.run_configurator import ComposedMetadata


_GENERATORS: dict[str, BackendConfigGenerator] = {
    "opencode": OpenCodeConfigGenerator(),
    "claude_code": ClaudeCodeConfigGenerator(),
    "codex": CodexConfigGenerator(),
    "pi": PiConfigGenerator(),
}


def get_generator(backend: str) -> BackendConfigGenerator | None:
    """Return the generator for ``backend`` or ``None``."""
    return _GENERATORS.get(backend)


def list_generators() -> list[str]:
    """Return registered backend names."""
    return list(_GENERATORS.keys())


__all__ = [
    "BackendConfigGenerator",
    "ClaudeCodeConfigGenerator",
    "CodexConfigGenerator",
    "OpenCodeConfigGenerator",
    "PiConfigGenerator",
    "get_generator",
    "list_generators",
]
