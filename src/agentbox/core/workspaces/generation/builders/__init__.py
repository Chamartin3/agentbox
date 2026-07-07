"""Builders that produce a WorkenvConfig from external sources (YAML /
interactive) for the ``agentbox ops workenv`` CLI.

DB-backed loading lives in ``WorkspaceComposer`` (``compose().config``) — it is
the single producer of a WorkenvConfig from DB state.
"""

from agentbox.core.workspaces.generation.builders.from_yaml import load_from_yaml
from agentbox.core.workspaces.generation.builders.interactive import build_interactive

__all__ = [
    "build_interactive",
    "load_from_yaml",
]
