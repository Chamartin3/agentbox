"""Engine CLI renderer."""

from agentbox.cli.shared.render import Renderer


class EngineRenderer(Renderer):
    """Typed render methods for engine contracts — methods are added as the engine branch migrates; formatting lives here, never in command bodies."""
