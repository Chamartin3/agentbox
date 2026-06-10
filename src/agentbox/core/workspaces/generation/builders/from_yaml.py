"""Load a WorkenvConfig from a YAML config file.

Thin wrapper around ``WorkenvConfig.from_yaml()`` so CLI code uses
a consistent builder import regardless of source.
"""

from __future__ import annotations

from pathlib import Path

from agentbox.core.workspaces.generation.config import WorkenvConfig


def load_from_yaml(path: Path) -> WorkenvConfig:
    """Load a WorkenvConfig from a YAML file."""
    return WorkenvConfig.from_yaml(path.read_text(encoding="utf-8"))
