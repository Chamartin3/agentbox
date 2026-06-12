"""Agents-domain runtime facade for the execution layer.

All types and functions the executor needs to compose prompts, capture
fragments, and validate output live here.  Execution code imports from
``core.agents`` (the top-level facade) — never from
``core.agents.composition.*`` or ``core.agents.config``.

Mirrors the inversion pattern established for Engines in
:mod:`agentbox.core.engines.backends.views`.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from agentbox.config import Settings
from agentbox.core.agents.composition.bundle import (
    _append_validation_engine_hint,
)
from agentbox.core.agents.composition.bundle.compose import (
    ComposedReference,
    ComposeResult,
)
from agentbox.core.agents.composition.bundle.loader import (
    load_bundle_from_bindings,
)
from agentbox.core.agents.composition.capture import (
    build_fragments as _build_fragments,
)
from agentbox.core.agents.composition.capture import (
    fragments_to_json as _fragments_to_json,
)
from agentbox.core.agents.composition.output_contract import (
    append as _append_output_contract,
)
from agentbox.core.agents.composition.resolver import (
    resolve_prompt,
)
from agentbox.core.agents.config import (
    ExecutionConfig,
    OutputConfig as _OutputConfig,
    PythonAgentConfig,
    ValidatorConfig,
    resolve_output_config as _resolve_output_config,
)
from agentbox.core.data import AgentDef, RunStore, SessionStore
from agentbox.core.engines.backends.schema_to_model import (
    InconsistentSchema,
    assert_schema_consistent,
)
from agentbox.core.agents.validation import (
    ValidationResult,
    call_http_validator,
    call_script_validator,
    resolve_schema,
    run_json_schema,
    validate_jsonschema,
    validate_pydantic,
)
from agentbox.core.workspaces.prep import (
    prompt_resolution_to_snapshot,
    resolve_agent_prompt_bindings,
)

logger = logging.getLogger(__name__)


# ── value types ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class AgentRuntimeView:
    """Execution's typed view of per-run agent configuration.

    Built once by the Agents domain; consumed by the executor, step-loop,
    and validation.  No execution code should call ``.from_agent()``
    directly — the compose-prompt facade returns this as part of
    :class:`ComposedPrompt`.
    """

    max_validation_retries: int = 0
    max_error_retries: int = 0
    output_validation_engine: str = "both"
    output_schema_path: str | None = None
    json_schema: dict[str, object] | None = None
    validators: tuple[ValidatorConfig, ...] = ()

    @classmethod
    def from_agent(
        cls, agent: AgentDef, *, store: RunStore | SessionStore | None = None
    ) -> AgentRuntimeView:
        exec_cfg = ExecutionConfig.from_agent(agent)
        python_cfg = PythonAgentConfig.from_agent(agent)
        out_cfg = _resolve_output_config(store, agent)
        return cls(
            max_validation_retries=exec_cfg.max_validation_retries,
            max_error_retries=exec_cfg.max_error_retries,
            output_validation_engine=exec_cfg.output_validation_engine,
            output_schema_path=python_cfg.output_schema_path,
            json_schema=out_cfg.json_schema,
            validators=out_cfg.validators,
        )

    @property
    def has_schema(self) -> bool:
        return (
            self.output_schema_path is not None
            or self.json_schema is not None
            or bool(self.validators)
        )


@dataclass(frozen=True)
class ComposedPrompt:
    """Composed prompt state produced by ``compose_prompt()``.

    Contains everything the executor needs from the composition
    pipeline: prompt texts, schemas, validation hints, and the
    agent's runtime view.  No execution code reaches into
    ``core.agents.composition.*`` internals to build this.
    """

    system_text: str | None = None
    system_base: str | None = None
    composed_schema: dict[str, object] | None = None
    composed_input_schema: dict[str, object] | None = None
    composed_user: str | None = None
    agent: AgentDef | None = None
    input_: str = ""
    composed_references: tuple[ComposedReference, ...] | None = None
    composed_bundle_sha: str | None = None
    validation_mode: str | None = None
    composition_result: ComposeResult | None = None
    prompt_bindings: list[dict[str, object]] = field(default_factory=list)
    snapshot_entries: list[dict[str, object]] = field(default_factory=list)
    runtime_view: AgentRuntimeView | None = None


# ── facade functions ──────────────────────────────────────────────────


def compose_prompt(
    *,
    store: RunStore,
    settings: Settings,
    agent: AgentDef,
    input_: str,
    variables: dict[str, str] | None,
) -> ComposedPrompt:
    """Compose the agent's prompt bundle + resolve bindings + output contract.

    This is the single entry point for the composition pipeline.  It
    replaces the inline logic that previously lived in
    ``core/execution/prepare/prompts.py::resolve_run_prompt`` and the
    five deep imports that function required.

    Returns a :class:`ComposedPrompt` with every field the executor
    needs — it should *not* drill into ``core.agents.composition.*``
    internals for any of the returned data.
    """
    snapshot_entries: list[dict[str, object]] = []
    agent_copied = False

    # ---- Stage 1: composition ------------------------------------------
    composition_result = None
    system_text: str | None = None
    system_base: str | None = None
    composed_schema: dict[str, object] | None = None
    composed_input_schema: dict[str, object] | None = None
    composed_user: str | None = None
    composed_references: tuple[ComposedReference, ...] | None = None
    composed_bundle_sha: str | None = None

    if agent.composition is not None and variables is not None:
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

    # ---- Stage 1b: validation-mode from agent.composition ---------------
    validation_mode: str | None = None
    if agent.composition is not None:
        validation_mode = agent.composition.output_validation

    # ---- Stage 2: prompt-resource binding substitution ------------------
    prompt_bindings: list[dict[str, object]] = []
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

    # ---- Stage 3: output-contract assembly ------------------------------
    out_cfg = _resolve_output_config(store, agent)
    if composed_schema is None and isinstance(out_cfg.json_schema, dict):
        composed_schema = out_cfg.json_schema

    if out_cfg.validators or isinstance(out_cfg.json_schema, dict):
        base_for_contract = system_text if system_text is not None else (agent.prompt or "")
        system_text = _append_output_contract(base_for_contract, out_cfg)

        if system_base is not None:
            constraints_only = _OutputConfig(json_schema=None, validators=out_cfg.validators)
            system_base = _append_output_contract(system_base, constraints_only)

    # ---- Stage 4: output_schema binding fallback (legacy_dir) ------------
    if prompt_bindings and composed_schema is None:
        for _b in prompt_bindings:
            if _b.get("slot") != "output_schema":
                continue
            _blobs = _b.get("blobs")
            if not isinstance(_blobs, list):
                break
            for _blob in _blobs:
                if not isinstance(_blob, dict):
                    continue
                _raw = (str(_blob.get("content_text") or "")).strip()
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

    # ---- Stage 5: fail-fast schema consistency check --------------------
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
    # is non-trivial.
    if not agent_copied and (
        system_text is not None
        or system_base is not None
        or composed_schema is not None
        or validation_mode is not None
    ):
        agent = agent.model_copy(deep=True)

    # Build the runtime view from the resolved config.
    runtime_view = AgentRuntimeView.from_agent(agent, store=store)

    return ComposedPrompt(
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
        runtime_view=runtime_view,
    )


def capture_fragments(
    *,
    agent: AgentDef,
    user_input: str,
    project_root: Path,
    argv: list[str] | None = None,
    store: SessionStore | None = None,
    composed: ComposedPrompt | None = None,
) -> str:
    """Build prompt fragments and return them as a JSON string.

    This wraps ``build_fragments`` + ``fragments_to_json`` from
    ``core.agents.composition.capture``.  Execution code calls this
    once and stores the result — it should never import capture
    internals directly.
    """
    frags = _build_fragments(
        agent=agent,
        user_input=user_input,
        project_root=project_root,
        argv=argv,
        store=store,
        composed=composed,
    )
    return _fragments_to_json(frags)


def validate_output(
    *,
    payload: str | None,
    view: AgentRuntimeView,
    workdir: Path | None = None,
    project_root: Path | None = None,
    agent: AgentDef | None = None,
    composed_schema: dict[str, object] | None = None,
) -> ValidationResult:
    """Validate ``payload`` against the agent's declared output contract.

    This wraps the two-gate validation architecture from
    ``core/execution/output_validate.py`` but consumes a pre-resolved
    :class:`AgentRuntimeView` instead of reaching into
    ``core.agents.config`` at call time.

    The legacy path (file-based schema resolution) is preserved via
    ``workdir`` / ``project_root`` / ``agent`` / ``composed_schema``
    kwargs.  New code should pass ``view`` only.
    """

    # ---- New path: pre-resolved OutputConfig from view -------------------
    if view.json_schema is not None or view.validators:
        if not payload:
            return ValidationResult(
                ok=False,
                error="output is empty but an output schema is required",
                engine="none",
            )
        # Gate 1: implicit jsonschema validator
        if view.json_schema is not None:
            result = run_json_schema(view.json_schema, payload)
            if not result.ok:
                return result
        # Gate 2..N: explicit validators
        ran_http = False
        ran_script = False
        for vcfg in view.validators:
            if vcfg.kind == "http":
                result = call_http_validator(vcfg, payload)
                if not result.ok:
                    return result
                ran_http = True
            elif vcfg.kind == "script":
                result = call_script_validator(vcfg, payload)
                if not result.ok:
                    return result
                ran_script = True
            else:
                return ValidationResult(
                    ok=False,
                    error=f"unknown validator kind: {vcfg.kind}",
                    engine="none",
                )
        if view.json_schema is not None and ran_http:
            engine = "json-schema+http-callback"
        elif view.json_schema is not None and ran_script:
            engine = "json-schema+script"
        elif ran_http:
            engine = "http-callback"
        elif ran_script:
            engine = "script"
        elif view.json_schema is not None:
            engine = "json-schema"
        else:
            engine = "off"
        return ValidationResult(ok=True, engine=engine)

    # ---- Legacy path: file-based schema resolution ----------------------
    schema, schema_err = resolve_schema(
        agent, workdir or Path("."), project_root, composed_schema=composed_schema
    )
    if schema is None:
        if schema_err:
            return ValidationResult(ok=False, error=schema_err, engine="none")
        return ValidationResult(ok=True, engine="off")

    if not payload:
        return ValidationResult(
            ok=False,
            error="output is empty but an output schema is required",
            engine="none",
        )

    engine_name = view.output_validation_engine

    if engine_name == "jsonschema":
        return validate_jsonschema(payload, schema)
    if engine_name == "pydantic":
        return validate_pydantic(payload, schema)

    js = validate_jsonschema(payload, schema)
    if not js.ok:
        return js
    py = validate_pydantic(payload, schema)
    if not py.ok:
        return py
    return ValidationResult(ok=True, engine="both")


__all__ = [
    "AgentRuntimeView",
    "ComposedPrompt",
    "capture_fragments",
    "compose_prompt",
    "validate_output",
]
