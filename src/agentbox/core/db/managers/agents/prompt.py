"""PromptVersionManager — prompt version history CRUD."""
from __future__ import annotations

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.agents.prompt import PromptVersion


class PromptVersionManager(Manager[PromptVersion]):
    """Manager for the ``prompt_versions`` table."""
    model = PromptVersion
