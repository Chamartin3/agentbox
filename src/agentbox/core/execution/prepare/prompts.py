"""Unified prompt resolution for a run.

This module owns the system-prompt assembly pipeline that used to be
scattered across ``prepare/resources.py``:

1. **Composition** — if the agent has a composition bundle and we have
   variables, render the bundle and seed the system prompt with the
   composed text (+ validation-engine hint).
2. **Prompt-resource binding substitution** — replace
   ``{{resource:foo}}`` markers using the agent's prompt-resource
   bindings. Operates on the composed system if present, otherwise on
   the inline ``agent.prompt`` (in which case the agent is copied with
   the rewritten prompt).
3. **Output-contract assembly** — append the validators / JSON Schema
   contract block. Always targets the composed system (falling back to
   ``agent.prompt`` if composition didn't run); ``system_base`` only
   gets the constraints-only contract (used by the token backend).
4. **Output-schema binding fallback** — for legacy-dir agents without a
   composed schema, lift the ``output_schema`` slot binding's JSON into
   ``composed_schema``.
5. **Fail-fast schema consistency check** — raise on internally
   inconsistent schemas before any backend sees them.

The function returns a :class:`ResolvedPrompt` carrying everything the
caller needs. The composed prompt/schema fields are surfaced as a
typed :class:`ComposedState` (``ResolvedPrompt.to_composed_state()``)
which the executor threads explicitly through ``render``,
``validate_output``, and capture — no ``agent.__dict__`` side-channel.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from agentbox.core.agents import compose_prompt
from agentbox.core.db import AgentDef

if TYPE_CHECKING:
    from agentbox.core.config import Settings
    from agentbox.core.db import RunStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ComposedState:
    """Composed-prompt state for one run.

    Single typed replacement for the seven ``agent.__dict__["_composed_*"]``
    keys the executor and backends used to share. Created by the prompt
    resolver and threaded explicitly through render / validate / capture
    so no hidden side-channel survives on the AgentDef.

    All fields are optional; ``None`` means "this aspect wasn't composed
    for this run." Backends should treat a missing ``ComposedState`` (or
    one with ``system is None``) as "no composition — fall back to the
    agent's inline prompt and on-disk files."
    """

    system: str | None = None
    system_base: str | None = None
    schema: dict | None = None
    input_schema: dict | None = None
    user: str | None = None
    references: Any = None
    bundle_sha: str | None = None
    validation_mode: str | None = None


@dataclass
class ResolvedPrompt:
    """Outcome of the unified prompt-resolution pipeline.

    ``agent`` is the (possibly copied) AgentDef to hand to the backend.
    It will be a fresh copy iff composition ran *or* prompt-binding
    substitution rewrote an inline ``agent.prompt``.

    ``system_text`` is the final assembled system prompt; ``None`` when
    no composition ran and the agent had no inline prompt to augment.

    ``system_base`` is the composition's pre-schema/reference system
    text (token backend only) with the constraints-only contract
    appended; ``None`` when composition didn't run.

    ``composed_*`` fields mirror :class:`ComposeResult` and are ``None``
    when composition didn't run.

    ``validation_mode`` is the composition's output-validation mode
    string, even when ``composition_result`` is ``None`` (the caller
    sets this whenever ``agent.composition`` exists).

    ``snapshot_entries`` are JSON-serializable rows the caller must
    append to its resource snapshot.
    """

    agent: AgentDef
    input_: str
    system_text: str | None
    system_base: str | None
    composed_schema: dict | None
    composed_input_schema: dict | None
    composed_user: str | None
    composed_references: Any
    composed_bundle_sha: str | None
    validation_mode: str | None
    composition_result: Any
    prompt_bindings: list[dict] = field(default_factory=list)
    snapshot_entries: list[dict] = field(default_factory=list)

    def to_composed_state(self) -> ComposedState:
        """Bundle the composed fields into the typed ComposedState."""
        return ComposedState(
            system=self.system_text,
            system_base=self.system_base,
            schema=self.composed_schema,
            input_schema=self.composed_input_schema,
            user=self.composed_user,
            references=self.composed_references,
            bundle_sha=self.composed_bundle_sha,
            validation_mode=self.validation_mode,
        )


def resolve_run_prompt(
    *,
    store: RunStore,
    settings: Settings,
    agent: AgentDef,
    input_: str,
    variables: dict[str, Any] | None,
) -> ResolvedPrompt:
    """Run the unified prompt-resolution pipeline via the Agents facade.

    Delegates to :func:`agentbox.core.agents.compose_prompt` so that
    the execution layer never imports from ``core.agents.composition.*``
    or ``core.agents.config`` internals.
    """
    composed = compose_prompt(
        store=store,
        settings=settings,
        agent=agent,
        input_=input_,
        variables=variables,
    )
    assert composed.agent is not None
    return ResolvedPrompt(
        agent=composed.agent,
        input_=composed.input_,
        system_text=composed.system_text,
        system_base=composed.system_base,
        composed_schema=composed.composed_schema,
        composed_input_schema=composed.composed_input_schema,
        composed_user=composed.composed_user,
        composed_references=composed.composed_references,
        composed_bundle_sha=composed.composed_bundle_sha,
        validation_mode=composed.validation_mode,
        composition_result=composed.composition_result,
        prompt_bindings=composed.prompt_bindings,
        snapshot_entries=composed.snapshot_entries,
    )
