"""Run CLI renderer."""

from agentbox.cli.shared.render import Renderer


class RunRenderer(Renderer):
    """Typed render methods for run contracts — methods are added as the run branch migrates; formatting lives here, never in command bodies."""
