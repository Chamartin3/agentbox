"""Engine-local views of agent config."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentbox.core.tools.canonical import CanonicalTool


@dataclass(frozen=True)
class RuntimeConfigView:
    """Engine-local view of agent runtime config (``allowed_tools`` +
    ``forbidden_tools``).

    This is the only slice of ``core.agents.definition.RuntimeConfig`` that
    backends consume.  Defining it here keeps engines free of Agents
    domain imports.
    """

    allowed_tools: tuple[CanonicalTool, ...] = ()
    forbidden_tools: tuple[CanonicalTool, ...] = ()


@dataclass(frozen=True)
class PythonAgentConfigView:
    """Engine-local view of agent python config (``agent_module``, schema path).

    This is the only slice of ``core.agents.definition.PythonAgentConfig``
    that backends consume.
    """

    agent_module: str | None = None
    output_schema_path: str | None = None


@dataclass(frozen=True)
class ComposedReferenceView:
    """Engine-local view of a composed prompt reference section.

    Mirrors ``core.agents.composition.bundle.compose.ComposedReference``
    so backend adapters do not import the Agents domain.
    """

    path: str
    heading: str
    content: str


@dataclass(frozen=True)
class ComposedView:
    """Engine-local view of composed prompt state.

    Execution builds this from its richer ComposedState at the render
    boundary so backend adapters do not import the Execution domain.
    """

    system: str | None = None
    system_base: str | None = None
    schema: dict[str, Any] | None = None
    input_schema: dict[str, Any] | None = None
    user: str | None = None
    references: tuple[ComposedReferenceView, ...] = ()
    bundle_sha: str | None = None
    validation_mode: str | None = None
