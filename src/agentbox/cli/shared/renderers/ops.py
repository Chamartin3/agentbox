"""Ops CLI renderer."""

from agentbox.cli.shared.render import Renderer


class OpsRenderer(Renderer):
    """Typed render methods for ops contracts — methods are added as the ops branch migrates; formatting lives here, never in command bodies."""
