"""Per-domain renderer components — each subclasses Renderer to inherit message primitives.

Import from this package rather than reaching into individual modules.
"""

from agentbox.cli.shared.renderers.agent import AgentRenderer
from agentbox.cli.shared.renderers.engine import EngineRenderer
from agentbox.cli.shared.renderers.ops import OpsRenderer
from agentbox.cli.shared.renderers.run import RunRenderer
from agentbox.cli.shared.renderers.system import SystemRenderer
from agentbox.cli.shared.renderers.workspace import WorkspaceRenderer

__all__ = [
    "AgentRenderer",
    "EngineRenderer",
    "OpsRenderer",
    "RunRenderer",
    "SystemRenderer",
    "WorkspaceRenderer",
]
