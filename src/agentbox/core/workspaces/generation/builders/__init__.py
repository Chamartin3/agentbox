"""Builders that produce a WorkenvConfig from external sources.

DB-backed loading lives in ``WorkspaceComposer`` (``compose().config``);
interactive prompting lives in the CLI render layer
(``cli.shared.renderers.ops``). What remains here is YAML loading for the
``agentbox ops workenv`` CLI.
"""

from agentbox.core.workspaces.generation.builders.from_yaml import load_from_yaml

__all__ = ["load_from_yaml"]
