"""Codex backend config generator.

Codex's ``codex exec`` CLI takes the user prompt from stdin and the
system context from the working directory's ``CLAUDE.md`` (when
present). This generator only needs to materialise a single fallback
``CLAUDE.md`` for backends that rely on it.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from agentbox.core.run.config.backends.base import (
    BackendConfigGenerator,
    McpConfig,
)

if TYPE_CHECKING:
    from agentbox.core.data.manifest import AgentDef
    from agentbox.core.run.config.run_configurator import ComposedMetadata


class CodexConfigGenerator(BackendConfigGenerator):
    def generate(
        self,
        backend_dir: Path,
        agent: AgentDef,
        composed: ComposedMetadata,
        mcp: McpConfig | None = None,
    ) -> None:
        self._write_claude_md(backend_dir, composed)

    def _write_claude_md(self, backend_dir: Path, composed: ComposedMetadata) -> None:
        claude_md = backend_dir / "CLAUDE.md"
        if claude_md.exists():
            return
        claude_md.write_text(composed.system or "", encoding="utf-8")
