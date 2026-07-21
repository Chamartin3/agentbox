"""Inline-to-composition synthesizer.

Converts an inline-prompt agent (one whose ``AgentDef.composition is None``)
into an equivalent agent that carries a minimal ``[composition]`` block so
the composition pipeline's Stage-1 gate always triggers.

The minimal block is ``CompositionConfig()`` with all defaults.  At runtime
``BindingsBundleSource.read_system()`` sources the system prompt from
``agent_versions.prompt_content`` regardless of what ``composition.system``
says, so the block only needs to *exist* — its path fields are never
consulted by the DB-backed compose path.

Byte-identity guarantee
-----------------------
For an inline-prompt agent that has no ``{template_variable}`` syntax in its
prompt, the composed system text produced by Stage 1 equals the value of
``agent.prompt`` (from ``config_json``) that Stage 2 / Stage 3 would have
used.  Both originate from the same ``agent_versions.prompt_content`` column.
"""

from __future__ import annotations

from agentbox.core.data.manifests.agents import AgentDef, CompositionConfig


def inline_to_composition(agent: AgentDef) -> AgentDef:
    """Return a copy of *agent* with a synthesized ``CompositionConfig``.

    If the agent already has a composition block this is a no-op (returns
    the same object, no copy).

    The synthesized block carries all ``CompositionConfig`` defaults — the
    concrete system-prompt text is always read from
    ``agent_versions.prompt_content`` by ``BindingsBundleSource``, so the
    ``system`` field value is not consulted at runtime.

    Args:
        agent: An ``AgentDef`` loaded from the database.

    Returns:
        An ``AgentDef`` whose ``composition`` attribute is non-None.
    """
    if agent.composition is not None:
        return agent
    return agent.model_copy(update={"composition": CompositionConfig()})


__all__ = ["inline_to_composition"]
