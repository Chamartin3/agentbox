"""BackendConfigGenerator ABC."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentbox.core.data import AgentDef
    from agentbox.core.engines.render.run_configurator import ComposedMetadata


@dataclass(frozen=True)
class McpConfig:
    """MCP server configuration shared across backends."""

    server_name: str = "mcp"
    url: str | None = None
    transport: str = "http"
    command: list[str] | None = None


class BackendConfigGenerator(ABC):
    """Translate prompts/ into a backend's native run-directory format."""

    @abstractmethod
    def generate(
        self,
        backend_dir: Path,
        agent: AgentDef,
        composed: ComposedMetadata,
        mcp: McpConfig | None = None,
    ) -> None:
        """Write backend-specific files into ``backend_dir``.

        Implementations must be idempotent — they should skip files that
        already exist unless regeneration is explicitly requested.
        """
        raise NotImplementedError
