"""MCP tool for prompt preview (resolved + rendered prompt with bindings)."""

from __future__ import annotations

from fastmcp import FastMCP

from typing import NotRequired, TypedDict

from agentbox.core.data.payload_types import PromptPreviewResult
from agentbox.core.service.agents import PreviewError
from agentbox.mcp.context import MCPContext


class PreviewToolError(TypedDict):
    error: str
    detail: NotRequired[str]
    agent_id: NotRequired[str]


def register_prompts(mcp: FastMCP, ctx: MCPContext) -> None:
    @mcp.tool
    def preview_prompt(
        agent_id: str,
        template_override: str | None = None,
    ) -> PromptPreviewResult | PreviewToolError:
        """Render the agent's fully composed prompt with all bindings applied.

        Returns the final ``rendered_prompt`` plus a ``char_breakdown``
        showing how many characters each piece contributes (base template,
        each appended reference, input/output schema blocks), plus a
        ``snapshot`` of every resolved binding (resource_id, version_id,
        content_hash, chars). Use ``template_override`` to preview with a
        candidate prompt body instead of the agent's current one."""
        if template_override is None:
            agent = ctx.agents.resolve_agent(agent_id)
            if agent is None:
                return {"error": "agent_not_found", "agent_id": agent_id}
            template = agent.prompt or ""
        else:
            template = template_override
        try:
            return ctx.agents.render_agent_prompt_preview(
                agent_id=agent_id, template=template
            )
        except PreviewError as exc:
            return {"error": exc.code, "detail": exc.detail}
