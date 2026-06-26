"""Agent CLI renderer."""

from agentbox.cli.shared.render import Renderer


class AgentRenderer(Renderer):
    """Typed render methods for agent contracts — methods are added as the agent branch migrates; formatting lives here, never in command bodies."""
