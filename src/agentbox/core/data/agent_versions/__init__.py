"""Agent-versions mixin: create, list, get, diff, comment, rate.

Composed into ``SessionStore``. Reads ``self.engine`` and operates on
``agent_versions`` + ``agent_version_comments`` + ``agent_version_ratings``.

The original single-file ``agent_versions.py`` module was split into a
sub-package for maintainability. ``AgentVersionsMixin`` remains the public
composable class; it derives from the read, agent-lifecycle, revisions,
files, meta, and diff sub-mixins below.
"""

from __future__ import annotations

from agentbox.core.data.agent_versions._diff import _AgentVersionsDiffMixin
from agentbox.core.data.agent_versions._models import (
    _copy_version_files,
    _prepare_files,
    _VALID_FILE_KINDS,
)
from agentbox.core.data.agent_versions._read import _AgentVersionsReadMixin
from agentbox.core.data.agent_versions._write_agent import _AgentVersionsAgentMixin
from agentbox.core.data.agent_versions._write_files import _AgentVersionsFilesMixin
from agentbox.core.data.agent_versions._write_meta import _AgentVersionsMetaMixin
from agentbox.core.data.agent_versions._write_revisions import (
    _AgentVersionsRevisionsMixin,
)


class AgentVersionsMixin(
    _AgentVersionsReadMixin,
    _AgentVersionsAgentMixin,
    _AgentVersionsRevisionsMixin,
    _AgentVersionsFilesMixin,
    _AgentVersionsMetaMixin,
    _AgentVersionsDiffMixin,
):
    """Versioned agent persistence. Requires ``self.engine: Engine``."""


__all__ = [
    "AgentVersionsMixin",
    "_VALID_FILE_KINDS",
    "_copy_version_files",
    "_prepare_files",
]
