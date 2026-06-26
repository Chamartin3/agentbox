"""Workspace CLI renderer."""

from agentbox.cli.shared.render import Renderer


class WorkspaceRenderer(Renderer):
    """Typed render methods for workspace contracts — methods are added as the workspace branch migrates; formatting lives here, never in command bodies."""
