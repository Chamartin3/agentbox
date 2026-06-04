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

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from agentbox.core.agents import (
    ExecutionConfig,
    OutputConfig as _OC,
    _append_output_contract,
    _append_validation_engine_hint,
    load_bundle_from_bindings,
    resolve_output_config as _resolve_out,
    resolve_prompt,
)
from agentbox.core.data import AgentDef
from agentbox.core.engines.backends.schema_to_model import (
    InconsistentSchema,
    assert_schema_consistent,
)
from agentbox.core.execution.prepare.envdoc import (
    prompt_resolution_to_snapshot,
    resolve_agent_prompt_bindings,
)

if TYPE_CHECKING:
    from agentbox.config import Settings
    from agentbox.core.data import SessionStore

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
    store: SessionStore,
    settings: Settings,
    agent: AgentDef,
    input_: str,
    variables: dict[str, Any] | None,
) -> ResolvedPrompt:
    """Run the unified prompt-resolution pipeline.

    The four stages (composition → binding substitution → output
    contract → schema fallback) and the fail-fast schema consistency
    check happen here. Behavior is preserved bit-for-bit from the
    legacy inline version in ``prepare_run_resources``.
    """
    snapshot_entries: list[dict] = []
    agent_copied = False

    # ----- Stage 1: composition ----------------------------------------
    composition_result = None
    system_text: str | None = None
    system_base: str | None = None
    composed_schema: dict | None = None
    composed_input_schema: dict | None = None
    composed_user: str | None = None
    composed_references: Any = None
    composed_bundle_sha: str | None = None

    if agent.composition is not None and variables is not None:
        from agentbox.core.agents.composition.bundle import (
            _append_validation_engine_hint,
        )
        from agentbox.core.agents.composition.bundle.loader import (
            load_bundle_from_bindings,
        )

        shared_roots = {
            k: settings.project_root / v
            for k, v in store.get_project_shared_assets().items()
        }

        bundle = load_bundle_from_bindings(agent_id=agent.id, store=store)
        composition_result = bundle.compose(variables, shared_roots)

        system_text = composition_result.system
        if composition_result.schema is not None:
            engine = ExecutionConfig.from_agent(agent).output_validation_engine
            system_text = _append_validation_engine_hint(system_text, engine)

        system_base = composition_result.system_base
        composed_schema = composition_result.schema
        composed_input_schema = composition_result.input_schema
        composed_user = composition_result.user
        composed_references = composition_result.references
        composed_bundle_sha = composition_result.bundle_sha

        agent = agent.model_copy(deep=True)
        agent_copied = True
        input_ = composition_result.user

    # ----- Stage 1b: validation-mode from agent.composition -------------
    validation_mode: str | None = None
    if agent.composition is not None:
        validation_mode = agent.composition.output_validation

    # ----- Stage 2: prompt-resource binding substitution ----------------
    prompt_bindings: list[dict] = []
    try:
        prompt_bindings = resolve_agent_prompt_bindings(store, agent.id)
        if prompt_bindings:
            if system_text is not None:
                resolution = resolve_prompt(system_text, prompt_bindings)
                system_text = resolution.rendered_prompt
                snapshot_entries.extend(
                    prompt_resolution_to_snapshot(resolution)
                )
                for marker in resolution.unresolved_markers:
                    logger.warning(
                        "executor: unresolved prompt resource marker {{resource:%s}} for agent %r",
                        marker,
                        agent.id,
                    )
            else:
                inline_prompt = agent.prompt
                if inline_prompt:
                    resolution = resolve_prompt(inline_prompt, prompt_bindings)
                    agent = agent.model_copy(
                        update={"prompt": resolution.rendered_prompt}
                    )
                    agent_copied = True
                    snapshot_entries.extend(
                        prompt_resolution_to_snapshot(resolution)
                    )
                    for marker in resolution.unresolved_markers:
                        logger.warning(
                            "executor: unresolved prompt resource marker {{resource:%s}} for agent %r",
                            marker,
                            agent.id,
                        )
    except Exception:
        logger.exception(
            "executor: prompt resource binding resolution failed for agent %r",
            agent.id,
        )

    # ----- Stage 3: output-contract assembly ----------------------------
    out_cfg = _resolve_out(store, agent)
    if composed_schema is None and isinstance(out_cfg.json_schema, dict):
        composed_schema = out_cfg.json_schema

    if out_cfg.validators or isinstance(out_cfg.json_schema, dict):
        base_for_contract = system_text if system_text is not None else (agent.prompt or "")
        system_text = _append_output_contract(base_for_contract, out_cfg)

        if system_base is not None:
            constraints_only = _OC(json_schema=None, validators=out_cfg.validators)
            system_base = _append_output_contract(system_base, constraints_only)

    # ----- Stage 4: output_schema binding fallback (legacy_dir) ---------
    if prompt_bindings and composed_schema is None:
        for _b in prompt_bindings:
            if _b.get("slot") != "output_schema":
                continue
            for _blob in _b.get("blobs") or []:
                _raw = (_blob.get("content_text") or "").strip()
                if not _raw:
                    continue
                try:
                    _schema = json.loads(_raw)
                except (json.JSONDecodeError, TypeError):
                    logger.warning(
                        "executor: failed to parse output_schema binding for agent %r",
                        agent.id,
                    )
                    continue
                if isinstance(_schema, dict):
                    composed_schema = _schema
                break
            break

    # ----- Stage 5: fail-fast schema consistency check ------------------
    if isinstance(composed_schema, dict):
        try:
            assert_schema_consistent(composed_schema)
        except InconsistentSchema as exc:
            msg = (
                f"output schema for agent {agent.id!r} is internally "
                f"inconsistent: {exc}"
            )
            logger.error("executor: %s", msg)
            raise ValueError(msg) from exc

    # Ensure the returned agent is a fresh copy whenever composed state
    # is non-trivial, to insulate callers from input aliasing.
    if not agent_copied and (
        system_text is not None
        or system_base is not None
        or composed_schema is not None
        or validation_mode is not None
    ):
        agent = agent.model_copy(deep=True)

    return ResolvedPrompt(
        agent=agent,
        input_=input_,
        system_text=system_text,
        system_base=system_base,
        composed_schema=composed_schema,
        composed_input_schema=composed_input_schema,
        composed_user=composed_user,
        composed_references=composed_references,
        composed_bundle_sha=composed_bundle_sha,
        validation_mode=validation_mode,
        composition_result=composition_result,
        prompt_bindings=prompt_bindings,
        snapshot_entries=snapshot_entries,
    )
