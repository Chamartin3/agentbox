"""CLAUDE.md renderer."""

from __future__ import annotations

from agentbox.core.workspace.env_doc.renderers.base import (
    EnvDocRenderer,
    RuntimeContext,
    _render_body,
)
from agentbox.core.workspace.env_doc.schema import EnvDocContent


class ClaudeMdRenderer(EnvDocRenderer):
    audience = "claude_only"

    def render(self, content: EnvDocContent, ctx: RuntimeContext) -> str:
        return _render_body(content, ctx, audience="claude_only")
