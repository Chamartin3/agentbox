"""pi backend config generator — symmetric with :mod:`codex`.

pi's CLI consumes the prompt via stdin and uses the working directory's
``CLAUDE.md`` for system context. This generator only writes that file.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from agentbox.core.engines.render.backends.base import (
    BackendConfigGenerator,
    McpConfig,
)

if TYPE_CHECKING:
    from agentbox.core.data import AgentDef
    from agentbox.core.engines.render.run_configurator import ComposedMetadata


class PiConfigGenerator(BackendConfigGenerator):
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
