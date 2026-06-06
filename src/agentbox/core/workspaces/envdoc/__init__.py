"""Workspace environment-instruction doc (Plan 04).

Single structured source-of-truth that renders into both `CLAUDE.md` and
`AGENTS.md` at run-prepare time.
"""

from agentbox.core.workspaces.envdoc.schema import (
    Command,
    CustomLink,
    EnvDocContent,
    References,
    Section,
    Visibility,
)

__all__ = [
    "Command",
    "CustomLink",
    "EnvDocContent",
    "References",
    "Section",
    "Visibility",
]
