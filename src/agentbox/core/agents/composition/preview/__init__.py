"""Shared agent-prompt preview renderer.

Used by both the REST `/api/agents/{agent_id}/prompt-resources/preview`
route and the `preview_prompt` MCP tool. Returns the fully composed
prompt plus a per-piece character breakdown and the resolution
snapshot — so callers can see exactly how many chars each appended
resource contributes.
"""

from agentbox.core.agents.composition.preview._helpers import (
    PreviewError as PreviewError,
)
from agentbox.core.agents.composition.preview.render import (
    render_agent_prompt_preview as render_agent_prompt_preview,
)

__all__ = [
    "PreviewError",
    "render_agent_prompt_preview",
]
