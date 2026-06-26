"""System CLI renderer."""

from agentbox.cli.shared.render import Renderer


class SystemRenderer(Renderer):
    """Typed render methods for system contracts — methods are added as the system branch migrates; formatting lives here, never in command bodies."""
