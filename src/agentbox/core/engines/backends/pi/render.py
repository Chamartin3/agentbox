"""pi backend config generator — symmetric with :mod:`agentbox.core.engines.backends.codex.render`.

pi's CLI consumes the prompt via stdin and uses the working directory's
``CLAUDE.md`` for system context. This generator only writes that file.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from agentbox.core.engines.backends.base import (
    BackendConfigGenerator,
    ComposedContext,
    McpConfig,
)

if TYPE_CHECKING:
    from agentbox.core.data import AgentDef


class PiConfigGenerator(BackendConfigGenerator):
    def generate(
        self,
        backend_dir: Path,
        agent: AgentDef,
        composed: ComposedContext,
        mcp: McpConfig | None = None,
    ) -> None:
        self._write_claude_md(backend_dir, composed)

    def _write_claude_md(self, backend_dir: Path, composed: ComposedContext) -> None:
        claude_md = backend_dir / "CLAUDE.md"
        if claude_md.exists():
            return
        claude_md.write_text(composed.system, encoding="utf-8")
