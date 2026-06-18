"""RunPromptManager — run prompt capture CRUD."""
from __future__ import annotations

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.runs.run_prompt import RunPrompt


class RunPromptManager(Manager[RunPrompt]):
    """Manager for the ``run_prompts`` table."""

    model = RunPrompt
