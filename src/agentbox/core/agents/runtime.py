"""Agents-domain runtime facade for the execution layer.

All types and functions the executor needs to compose prompts, capture
fragments, and validate output live here.  Execution code imports from
``core.agents`` (the top-level facade) — never from
``core.agents.composition.*`` or ``core.agents.config`` internals.

Mirrors the inversion pattern established for Engines in
:mod:`agentbox.core.engines.contracts.views`.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from agentbox.core.config import Settings
from agentbox.core.agents.composition.bundle import (
    _append_validation_engine_hint,
)
from agentbox.core.agents.composition.bundle.compose import (
    ComposedReference,
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
    resolve_output_config as _resolve_output_config,
)
from agentbox.core.data.payload_types import JsonSchemaDict, PromptEmbedSnapshotEntry, ResolvedBindingView
from agentbox.core.data.rows import AgentPromptBindingRow, RepoResourceRow, ResourceVersionRow, ResourceBlobRow
from agentbox.core.data import AgentDef
from agentbox.core.db import PromptVersionManager
from agentbox.core.db.system.config import load_project_shared_assets
from agentbox.core.engines.contracts.schema_to_model import (
    InconsistentSchema,
    assert_schema_consistent,
)
from agentbox.core.data.snapshots import prompt_resolution_to_snapshot
from agentbox.core.data.composition import (
    AgentRuntimeView,
    ComposedPrompt,
)

logger = logging.getLogger(__name__)


# ── value types ───────────────────────────────────────────────────────


class _DbStoreAdapter:
    """Duck-typed shim satisfying the store interface used by prompt
    composition internals (``load_bundle_from_bindings``,
    ``_resolve_output_config``, ``validate_output``).
    """

    def __init__(self, db: Any) -> None:
        self._db = db

    def list_prompt_bindings(self, agent_id: str) -> list[AgentPromptBindingRow]:
        return self._db.agent_prompt_resource_bindings.list_for_agent(agent_id)

    def get_repo_resource(self, resource_id: str) -> RepoResourceRow | None:
        return self._db.resources.get_resource(resource_id)

    def get_active_repo_version(self, resource_id: str) -> ResourceVersionRow | None:
        return self._db.resource_versions.get_active_version(resource_id)

    def get_repo_version(self, version_id: str) -> ResourceVersionRow | None:
        return self._db.resource_versions.get_version(version_id)

    def iter_repo_blobs(self, version_id: str) -> Iterator[ResourceBlobRow]:
        return self._db.resource_blobs.iter_blobs(version_id)

    def read_repo_blob(self, version_id: str, relative_path: str = "") -> Any:
        return self._db.resource_blobs.get_blob(version_id, relative_path)

    def get_active_version(self, agent_id: str) -> Any:
        return self._db.agent_versions.get_active(agent_id)

    def latest_version(self, agent_id: str) -> Any:
        return self._db.agent_versions.get_latest(agent_id)

    def list_version_files(self, version_id: int) -> Any:
        return self._db.agent_version_files.list_for_version(version_id)


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


def compose_prompt(
    *,
    db: Any,
    settings: Settings,
    agent: AgentDef,
    input_: str,
    variables: dict[str, str] | None,
) -> ComposedPrompt:
    """Compose the agent's prompt bundle + resolve bindings + output contract.

    This is the single entry point for the composition pipeline.

    Returns a :class:`ComposedPrompt` with every field the executor
    needs — it should *not* drill into ``core.agents.composition.*``
    internals for any of the returned data.
    """
    store = _DbStoreAdapter(db)
    snapshot_entries: list[PromptEmbedSnapshotEntry] = []
    agent_copied = False

    # ---- Stage 1: composition ------------------------------------------
    composition_result = None
    system_text: str | None = None
    system_base: str | None = None
    composed_schema: JsonSchemaDict | None = None
    composed_input_schema: JsonSchemaDict | None = None
    composed_user: str | None = None
    composed_references: tuple[ComposedReference, ...] | None = None
    composed_bundle_sha: str | None = None

    if agent.composition is not None and variables is not None:
        shared_roots = {
            k: settings.project_root / v
            for k, v in load_project_shared_assets().items()
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
    prompt_bindings: list[ResolvedBindingView] = []
    try:
        prompt_bindings = _resolve_prompt_bindings(store, agent.id)
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
    if composed_schema is None and out_cfg.json_schema is not None:
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
                    _schema: JsonSchemaDict | None = json.loads(_raw)
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
            assert_schema_consistent(dict(composed_schema))
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


def capture_fragments(
    *,
    agent: AgentDef,
    user_input: str,
    project_root: Path,
    argv: list[str] | None = None,
    prompt_versions: PromptVersionManager | None = None,
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
        prompt_versions=prompt_versions,
        composed=composed,
    )
    return _fragments_to_json(frags)


__all__ = [
    "AgentRuntimeView",
    "ComposedPrompt",
    "build_runtime_view",
    "capture_fragments",
    "compose_prompt",
]
