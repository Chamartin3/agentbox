"""AGENTS.md renderer."""

from __future__ import annotations

from agentbox.core.workspaces.envdoc.renderers.base import (
    EnvDocRenderer,
    RuntimeContext,
    _render_body,
)
from agentbox.core.workspaces.envdoc.schema import EnvDocContent


class AgentsMdRenderer(EnvDocRenderer):
    audience = "agents_only"

    def render(self, content: EnvDocContent, ctx: RuntimeContext) -> str:
        return _render_body(content, ctx, audience="agents_only")
