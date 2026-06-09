"""Engine-local views of agent config."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeConfigView:
    """Engine-local view of agent runtime config (``allowed_tools``).

    This is the only slice of ``core.agents.config.RuntimeConfig`` that
    backends consume.  Defining it here keeps engines free of Agents
    domain imports.
    """

    allowed_tools: tuple[str, ...] = ()


@dataclass(frozen=True)
class PythonAgentConfigView:
    """Engine-local view of agent python config (``agent_module``, schema path).

    This is the only slice of ``core.agents.config.PythonAgentConfig``
    that backends consume.
    """

    agent_module: str | None = None
    output_schema_path: str | None = None
