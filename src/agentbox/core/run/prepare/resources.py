"""Pre-backend resource preparation, extracted from RunExecutor.execute().

This module owns everything that used to live in the ~256-line block at
``executor.py:338-594`` (before the refactor): workspace resource
materialization, env-doc rendering, subagent wiring, prompt composition,
prompt-resource binding substitution, and output-contract assembly,
including the fail-fast schema consistency check.

Contract:
- Pure-ish: reads from ``store``, the filesystem, and ``settings``; writes
  rendered files to ``workdir`` and stages CLAUDE.md / AGENTS.md / subagent
  files. Does *not* write to the SessionStore — snapshot persistence is the
  executor's job (it persists ``PreparedResources.resource_snapshot_entries``
  after the run row is created).
- Preserves the legacy ``agent.__dict__`` channel that backends still read
  from. The eventual goal (Plan 08 Phase 4) is to move these fields into
  ``RenderedConfig.agent_meta`` and remove the mutation, but that requires
  a coordinated change across every backend adapter.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agentbox.core.agent.config import ExecutionConfig
from agentbox.core.data.manifest import AgentDef
from agentbox.core.prompt.resolver import resolve_prompt
from agentbox.core.resource.subagent_render import materialize_subagents
from agentbox.core.resource.workspace_materialize import materialize_workspace
from agentbox.core.run.backends._schema_to_model import (
    InconsistentSchema,
    assert_schema_consistent,
)
from agentbox.core.run.run_prep import (
    prompt_resolution_to_snapshot,
    render_env_doc,
    resolve_agent_prompt_bindings,
    resolve_workspace_resources,
    resolve_workspace_subagents,
    workspace_outcomes_to_snapshot,
)

if TYPE_CHECKING:
    from agentbox.config import Settings
    from agentbox.core.data.store import SessionStore

logger = logging.getLogger(__name__)


@dataclass
class PreparedResources:
    """Result of :func:`prepare_run_resources`.

    Carries everything downstream code in ``RunExecutor.execute`` needs after
    the pre-backend prep block:

    - ``agent``: the (possibly copied + ``__dict__``-mutated) AgentDef the
      backend adapter should consume. Always a fresh object when composition
      ran; otherwise the original ``agent``.
    - ``input_``: the input string, possibly replaced by ``composed_result.user``.
    - ``resource_snapshot_entries``: JSON-serializable snapshot rows for
      ``save_resource_snapshots``.
    - ``prompt_bindings``: resolver-ready prompt-binding dicts, kept around so
      the executor can scan for ``slot == "output_schema"`` bindings when no
      composed schema is present.
    - ``composed_result``: the composition output, or ``None`` if the agent
      didn't run through the composition pipeline.
    - ``workspace_id``: ``agent.workspace`` unless it's ``"<ephemeral>"``.
    """

    agent: AgentDef
    input_: str
    resource_snapshot_entries: list[dict] = field(default_factory=list)
    prompt_bindings: list[dict] = field(default_factory=list)
    composed_result: Any = None
    workspace_id: str | None = None


def prepare_run_resources(
    *,
    store: SessionStore,
    settings: Settings,
    agent: AgentDef,
    input_: str,
    variables: dict[str, Any] | None,
    workdir: Path,
) -> PreparedResources:
    """Run the pre-backend prep pipeline.

    This is a verbatim extraction of ``RunExecutor.execute`` lines 338-594
    (prior to this refactor). Behavior is intentionally preserved bit-for-bit
    — same exception swallowing, same logging, same ``agent.__dict__``
    mutations, same ordering. The only change is *where the code lives*.
    """
    resource_snapshot_entries: list[dict] = []
    workspace_id = agent.workspace if agent.workspace != "<ephemeral>" else None

    # ----- workspace resources, env doc, subagents ----------------------
    if workspace_id:
        try:
            ws_bindings = resolve_workspace_resources(store, workspace_id)
            if ws_bindings:
                outcomes = materialize_workspace(
                    workdir,
                    ws_bindings,
                    cache_root=settings.resource_cache_dir,
                )
                resource_snapshot_entries.extend(
                    workspace_outcomes_to_snapshot(outcomes)
                )
        except Exception:
            logger.exception(
                "executor: workspace resource materialization failed for workspace %r",
                workspace_id,
            )

        try:
            env_doc_entries = render_env_doc(store, workspace_id, workdir)
            resource_snapshot_entries.extend(env_doc_entries)
        except Exception:
            logger.exception(
                "executor: env doc rendering failed for workspace %r",
                workspace_id,
            )

        try:
            resolved_subagents = resolve_workspace_subagents(store, workspace_id)
            if resolved_subagents:
                sub_outcomes = materialize_subagents(workdir, resolved_subagents)
                for o in sub_outcomes:
                    resource_snapshot_entries.append(
                        {
                            "role": "workspace_subagent",
                            "workspace_id": o.workspace_id,
                            "agent_id": o.agent_id,
                            "alias": o.alias,
                            "files_written": o.files_written,
                        }
                    )
        except Exception:
            logger.exception(
                "executor: workspace subagent materialization failed for workspace %r",
                workspace_id,
            )

    # ----- composition path --------------------------------------------
    composed_result = None
    if agent.composition is not None and variables is not None:
        from agentbox.core.prompt.composition.loader import (
            load_bundle_from_bindings,
        )

        shared_roots = {
            k: settings.project_root / v
            for k, v in store.get_project_shared_assets().items()
        }

        bundle = load_bundle_from_bindings(agent_id=agent.id, store=store)
        composed_result = bundle.compose(variables, shared_roots)

        system_text = composed_result.system
        if composed_result.schema is not None:
            engine = ExecutionConfig.from_agent(agent).output_validation_engine
            from agentbox.core.prompt.composition import (
                _append_validation_engine_hint,
            )

            system_text = _append_validation_engine_hint(system_text, engine)

        agent = agent.model_copy(deep=True)
        agent.__dict__["_composed_system"] = system_text
        agent.__dict__["_composed_system_base"] = composed_result.system_base
        agent.__dict__["_composed_references"] = composed_result.references
        agent.__dict__["_composed_input_schema"] = composed_result.input_schema
        agent.__dict__["_composed_user"] = composed_result.user
        agent.__dict__["_composed_schema"] = composed_result.schema
        agent.__dict__["_composed_bundle_sha"] = composed_result.bundle_sha
        input_ = composed_result.user

    # ----- composition validation-mode wiring ---------------------------
    comp = agent.composition
    if comp is not None:
        if composed_result is None:
            agent = agent.model_copy(deep=True)
        agent.__dict__["_composed_validation_mode"] = comp.output_validation

    # ----- prompt resource binding substitution -------------------------
    prompt_bindings: list[dict] = []
    try:
        prompt_bindings = resolve_agent_prompt_bindings(store, agent.id)
        if prompt_bindings:
            composed_system = agent.__dict__.get("_composed_system")
            if composed_system is not None:
                resolution = resolve_prompt(composed_system, prompt_bindings)
                agent.__dict__["_composed_system"] = resolution.rendered_prompt
                resource_snapshot_entries.extend(
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
                    resource_snapshot_entries.extend(
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

    # ----- output-contract wiring ---------------------------------------
    from agentbox.core.agent.config import resolve_output_config as _resolve_out

    _out_cfg = _resolve_out(store, agent)
    if not isinstance(agent.__dict__.get("_composed_schema"), dict) and isinstance(
        _out_cfg.json_schema, dict
    ):
        agent.__dict__["_composed_schema"] = _out_cfg.json_schema

    if _out_cfg.validators or isinstance(_out_cfg.json_schema, dict):
        from agentbox.core.prompt.output_contract import append as _append_contract

        _composed_system = agent.__dict__.get("_composed_system")
        if not isinstance(_composed_system, str):
            _composed_system = agent.prompt or ""
        agent.__dict__["_composed_system"] = _append_contract(
            _composed_system, _out_cfg
        )
        _composed_system_base = agent.__dict__.get("_composed_system_base")
        if isinstance(_composed_system_base, str):
            from agentbox.core.agent.config import OutputConfig as _OC2

            _constraints_only = _OC2(
                json_schema=None,
                validators=_out_cfg.validators,
            )
            agent.__dict__["_composed_system_base"] = _append_contract(
                _composed_system_base, _constraints_only
            )

    # ----- output_schema binding → _composed_schema (legacy_dir agents)
    if prompt_bindings and not isinstance(
        agent.__dict__.get("_composed_schema"), dict
    ):
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
                    agent.__dict__["_composed_schema"] = _schema
                break
            break

    # ----- fail-fast schema consistency check ---------------------------
    _composed_schema = agent.__dict__.get("_composed_schema")
    if isinstance(_composed_schema, dict):
        try:
            assert_schema_consistent(_composed_schema)
        except InconsistentSchema as exc:
            msg = (
                f"output schema for agent {agent.id!r} is internally "
                f"inconsistent: {exc}"
            )
            logger.error("executor: %s", msg)
            raise ValueError(msg) from exc

    return PreparedResources(
        agent=agent,
        input_=input_,
        resource_snapshot_entries=resource_snapshot_entries,
        prompt_bindings=prompt_bindings,
        composed_result=composed_result,
        workspace_id=workspace_id,
    )
