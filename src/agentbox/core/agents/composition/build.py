"""Agents-domain prompt build pipeline.

Composes prompts from agent definitions, resolves resource bindings,
and assembles the complete prompt structure for the executor.
"""

from __future__ import annotations

import dataclasses
import json
import logging
from collections.abc import Iterator
from typing import Any

from agentbox.core.config import Settings
from agentbox.core.data.composition import (
    ComposedReference,
)
from agentbox.core.agents.composition.bundle import (
    load_bundle_from_bindings,
)
from agentbox.core.agents.composition.composer import PromptComposer
from agentbox.core.agents.composition.resolver import (
    resolve_prompt,
)
from agentbox.core.agents.definition import (
    ExecutionConfig,
    PythonAgentConfig,
)
from agentbox.core.agents.validation import (
    OutputConfig as _OutputConfig,
    resolve_output_config as _resolve_output_config,
)
from agentbox.core.agents.composition.rendering import (
    append as _append_output_contract,
    append_validation_engine_hint,
)
from jsonschema.exceptions import SchemaError

from agentbox.core.data.schema_validation import load_json_schema
from agentbox.core.data.payload_types import JsonSchemaDict, PromptEmbedSnapshotEntry, ResolvedBindingView, ResolvedPromptBinding
from agentbox.core.data.rows import AgentPromptBindingRow, RepoResourceRow, ResourceVersionRow, ResourceBlobRow
from agentbox.core.data import AgentDef
from agentbox.core.data import InconsistentSchema, assert_schema_consistent
from agentbox.core.data.snapshots import prompt_resolution_to_snapshot
from agentbox.core.data.composition import (
    AgentRuntimeView,
    ComposedPrompt,
    ComposeResult,
)
from agentbox.core.db import (
    AgentPromptResourceBindingManager,
    AgentVersionFileManager,
    AgentVersionManager,
    ResourceBlobManager,
    ResourceManager,
    ResourceVersionManager,
)

logger = logging.getLogger(__name__)


# ── value types ───────────────────────────────────────────────────────


@dataclasses.dataclass(frozen=True)
class BuildManagers:
    """The specific managers the prompt-build store adapter reads.

    Passed instead of the whole ``Database`` so no store object crosses the
    composition boundary (UNIFIED rule #4).
    """

    agent_prompt_resource_bindings: AgentPromptResourceBindingManager
    resources: ResourceManager
    resource_versions: ResourceVersionManager
    resource_blobs: ResourceBlobManager
    agent_versions: AgentVersionManager
    agent_version_files: AgentVersionFileManager


class _DbStoreAdapter:
    """Duck-typed shim satisfying the store interface used by prompt
    composition internals (``load_bundle_from_bindings``,
    ``_resolve_output_config``, ``check_output``).
    """

    def __init__(self, mgrs: BuildManagers) -> None:
        self._mgrs = mgrs

    def list_prompt_bindings(self, agent_id: str) -> list[AgentPromptBindingRow]:
        return self._mgrs.agent_prompt_resource_bindings.list_for_agent(agent_id)

    def get_repo_resource(self, resource_id: str) -> RepoResourceRow | None:
        return self._mgrs.resources.get_resource(resource_id)

    def get_active_repo_version(self, resource_id: str) -> ResourceVersionRow | None:
        return self._mgrs.resource_versions.get_active_version(resource_id)

    def get_repo_version(self, version_id: str) -> ResourceVersionRow | None:
        return self._mgrs.resource_versions.get_version(version_id)

    def iter_repo_blobs(self, version_id: str) -> Iterator[ResourceBlobRow]:
        return self._mgrs.resource_blobs.iter_blobs(version_id)

    def read_repo_blob(self, version_id: str, relative_path: str = "") -> Any:
        return self._mgrs.resource_blobs.get_blob(version_id, relative_path)

    def get_active_version(self, agent_id: str) -> Any:
        return self._mgrs.agent_versions.get_active(agent_id)

    def latest_version(self, agent_id: str) -> Any:
        return self._mgrs.agent_versions.get_latest(agent_id)

    def list_version_files(self, version_id: int) -> Any:
        return self._mgrs.agent_version_files.list_for_version(version_id)


def build_runtime_view(agent: AgentDef, *, store: Any = None) -> AgentRuntimeView:
    """Build AgentRuntimeView from agent definition and store.

    Reads execution and python agent config, resolves output contract via store,
    and constructs the runtime view for execution and validation.
    """
    exec_cfg = ExecutionConfig.from_agent(agent)
    python_cfg = PythonAgentConfig.from_agent(agent)
    out_cfg = _resolve_output_config(store, agent)
    return AgentRuntimeView(
        max_validation_retries=exec_cfg.max_validation_retries,
        max_error_retries=exec_cfg.max_error_retries,
        output_validation_engine=exec_cfg.output_validation_engine,
        output_schema_path=python_cfg.output_schema_path,
        json_schema=out_cfg.json_schema,
        validators=out_cfg.validators,
    )


def resolve_agent_prompt_bindings(
    agent_prompt_resource_bindings: AgentPromptResourceBindingManager,
    resources: ResourceManager,
    resource_versions: ResourceVersionManager,
    resource_blobs: ResourceBlobManager,
    agent_id: str,
) -> list[ResolvedPromptBinding]:
    """Hydrate all active prompt bindings for an agent into resolver-ready dicts.

    Returns the same shape as ``_resolve_binding_for_prompt`` in the API
    route, so ``resolve_prompt`` can consume them directly.
    """
    bindings = agent_prompt_resource_bindings.list_for_agent(agent_id)
    if not bindings:
        return []

    resolved: list[ResolvedPromptBinding] = []
    for b in bindings:
        resource = resources.get_resource(b["resource_id"])
        if not resource:
            logger.warning(
                "workspace prep: prompt binding %s references missing resource %s — skipping",
                b["id"],
                b["resource_id"],
            )
            continue
        version_id = b.get("pinned_version_id")
        if version_id:
            version_id = str(version_id)
        if not version_id:
            active = resource_versions.get_active_version(b["resource_id"])
            if not active:
                logger.warning(
                    "workspace prep: resource %s has no active version — skipping prompt binding %s",
                    resource["slug"],
                    b["id"],
                )
                continue
            version_id = str(active["id"])
        version = resource_versions.get_version(version_id)
        if version is None:
            continue
        blobs = list(resource_blobs.iter_blobs(version_id))
        resolved.append(
            {
                "binding_id": b["id"],
                "marker": b.get("marker"),
                "slot": b.get("slot"),
                "attach_as_reference": bool(b.get("attach_as_reference")),
                "resource_id": b["resource_id"],
                "version_id": version_id,
                "content_hash": version["content_hash"],
                "type": resource["type"],
                "mode": b.get("mode"),
                "display_name": resource["display_name"],
                "required": bool(b.get("required", 1)),
                "blobs": blobs,
            }
        )
    return resolved


# ── facade functions ──────────────────────────────────────────────────


def _resolve_prompt_bindings(store: Any, agent_id: str) -> list[ResolvedBindingView]:
    """Hydrate agent prompt bindings from duck-typed store methods."""
    raw = store.list_prompt_bindings(agent_id)
    if not raw:
        return []
    resolved: list[ResolvedBindingView] = []
    for b in raw:
        resource = store.get_repo_resource(b["resource_id"])
        if not resource:
            logger.warning(
                "executor: prompt binding %s references missing resource %s — skipping",
                b["id"],
                b["resource_id"],
            )
            continue
        version_id = b.get("pinned_version_id")
        if version_id:
            version_id = str(version_id)
        if not version_id:
            active = store.get_active_repo_version(b["resource_id"])
            if not active:
                logger.warning(
                    "executor: resource %s has no active version — skipping prompt binding %s",
                    resource["slug"],
                    b["id"],
                )
                continue
            version_id = str(active["id"])
        version = store.get_repo_version(version_id)
        if version is None:
            continue
        blobs = list(store.iter_repo_blobs(version_id))
        resolved.append(
            {
                "binding_id": b["id"],
                "marker": b.get("marker"),
                "slot": b.get("slot"),
                "attach_as_reference": bool(b.get("attach_as_reference")),
                "resource_id": b["resource_id"],
                "resource_slug": resource["slug"],
                "version_id": version_id,
                "content_hash": version["content_hash"],
                "type": resource["type"],
                "mode": b.get("mode"),
                "display_name": resource["display_name"],
                "required": bool(b.get("required", 1)),
                "blobs": blobs,
            }
        )
    return resolved


def build_prompt(
    *,
    managers: BuildManagers,
    settings: Settings,
    agent: AgentDef,
    input_: str,
    variables: dict[str, str] | None,
) -> ComposedPrompt:
    """Build the agent's prompt bundle + resolve bindings + output contract.

    This is the single entry point for the composition pipeline.

    Returns a :class:`ComposedPrompt` with every field the executor
    needs — it should *not* drill into ``core.agents`` submodule
    internals for any of the returned data.
    """
    store = _DbStoreAdapter(managers)
    snapshot_entries: list[PromptEmbedSnapshotEntry] = []

    # ---- Stage 1: composition ------------------------------------------
    # Every agent must have a composition block (enforced by the 0011
    # migration and all creation paths since plan 147).
    if agent.composition is None:
        raise ValueError(
            f"agent {agent.id!r} has no composition block. "
            "Run `agentbox ops migrate upgrade` to apply the 0011 migration "
            "and ensure all creation paths call inline_to_composition()."
        )

    composition_result = None
    system_base: str | None = None
    composed_schema: JsonSchemaDict | None = None
    composed_input_schema: JsonSchemaDict | None = None
    composed_user: str | None = None
    composed_references: tuple[ComposedReference, ...] | None = None
    composed_bundle_sha: str | None = None

    bundle = load_bundle_from_bindings(agent_id=agent.id, store=store)
    if bundle.source is None:
        raise ValueError(f"Bundle for {agent.id!r} has no source")

    # When variables is None (legacy raw-input_ path), compose without
    # template substitution so the system prompt is returned verbatim.
    _render = variables is not None
    _vars: dict[str, str] = variables if variables is not None else {}
    _pc = PromptComposer().compose(bundle.source, _vars, render=_render)

    # _pc.text is always a str (never None); system_text follows suite.
    _composed_text: str = _pc.text
    if _pc.output_schema is not None:
        engine = ExecutionConfig.from_agent(agent).output_validation_engine
        _composed_text = append_validation_engine_hint(_composed_text, engine)
    system_text = _composed_text

    system_base = _pc.base if _pc.base else None
    composed_schema = _pc.output_schema
    composed_input_schema = _pc.input_schema
    composed_user = _pc.user
    composed_references = tuple(
        s.to_composed_reference() for s in _pc.references
    )
    composed_bundle_sha = _pc.bundle_sha

    # Build a ComposeResult for backward-compatible composition_result field.
    composition_result = ComposeResult(
        system=_pc.text,
        user=_pc.user,
        schema=_pc.output_schema,
        schema_sha=_pc.output_schema_sha,
        bundle_sha=_pc.bundle_sha,
        system_base=_pc.base,
        references=composed_references,
        input_schema=_pc.input_schema,
    )

    agent = agent.model_copy(deep=True)
    if variables is not None:
        input_ = _pc.user

    # ---- Stage 1b: validation-mode from agent.composition ---------------
    # composition is guaranteed non-None by the guard above (model_copy preserves it).
    _composition = agent.composition
    assert _composition is not None  # narrowing for type-checkers
    validation_mode: str | None = _composition.output_validation

    # ---- Stage 2: prompt-resource binding substitution ------------------
    prompt_bindings: list[ResolvedBindingView] = []
    try:
        prompt_bindings = _resolve_prompt_bindings(store, agent.id)
        if prompt_bindings:
            # system_text is always set after Stage 1 (composition is required).
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
    except Exception:
        logger.exception(
            "executor: prompt resource binding resolution failed for agent %r",
            agent.id,
        )

    # ---- Stage 3: output-contract assembly ------------------------------
    out_cfg = _resolve_output_config(store, agent)
    if composed_schema is None and out_cfg.json_schema is not None:
        composed_schema = out_cfg.json_schema

    if out_cfg.validators or isinstance(out_cfg.json_schema, dict):
        # system_text is always set after Stage 1 (composition is required).
        system_text = _append_output_contract(system_text, out_cfg)

        if system_base is not None:
            constraints_only = _OutputConfig(json_schema=None, validators=out_cfg.validators)
            system_base = _append_output_contract(system_base, constraints_only)

    # ---- Stage 4: output_schema binding fallback ------------------------
    # Used when no inline composed schema exists but an agent binds an
    # output_schema resource.
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
                    _schema: JsonSchemaDict | None = load_json_schema(_raw)
                except (json.JSONDecodeError, TypeError, SchemaError):
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
            assert_schema_consistent(dict(composed_schema))
        except InconsistentSchema as exc:
            msg = (
                f"output schema for agent {agent.id!r} is internally "
                f"inconsistent: {exc}"
            )
            logger.error("executor: %s", msg)
            raise ValueError(msg) from exc

    # agent_copied is always True (Stage 1 always calls model_copy).

    # Build the runtime view from the resolved config.
    runtime_view = build_runtime_view(agent, store=store)

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


__all__ = [
    "AgentRuntimeView",
    "ComposedPrompt",
    "build_runtime_view",
    "build_prompt",
    "resolve_agent_prompt_bindings",
    "_DbStoreAdapter",
]
