"""Structured accessors for agent semantics stored in ``config_json``.

Phase 2 of the runner-DB-as-source-of-truth refactor (see
``runner-db-source-of-truth.md``). These dataclasses split what was
historically jammed into ``AgentDef.runner`` into three logical buckets:

- ``ExecutionConfig`` — validation/retry semantics (executor-level).
- ``RuntimeConfig`` — runtime/tooling knobs (MCP config, allowed tools).
- ``PythonAgentConfig`` — pydantic-ai / token backend dispatch metadata
  (module, deps factory, output schema path).

The values live in ``agent_versions.config_json`` under sub-keys
``execution`` / ``runtime`` / ``python``. ``config_json`` is the sole
source of truth — there is no legacy ``agent.runner`` fallback.

Runner-level config (backend, model, timeout, provider, extra_args)
stays out of here entirely — that's ``EffectiveRunnerConfig`` resolved
from ``runner_profiles`` by ``RunnerProfileResolver``.
"""

from __future__ import annotations

import json as _json
from dataclasses import dataclass
from typing import Any, Literal


def _config_section(agent: Any, section: str) -> dict[str, Any]:
    """Return the ``config_json[section]`` dict for an agent, if any.

    AgentDef itself doesn't carry config_json — it's a column on
    ``agent_versions``. Some call sites already attach the active row
    via ``agent.__dict__["_config_json"]`` after a DB load. Honour
    that when present; otherwise return an empty dict.
    """
    raw = agent.__dict__.get("_config_json") if hasattr(agent, "__dict__") else None
    if raw is None:
        return {}
    if isinstance(raw, str):
        try:
            raw = _json.loads(raw)
        except (ValueError, TypeError):
            return {}
    if not isinstance(raw, dict):
        return {}
    sub = raw.get(section)
    return sub if isinstance(sub, dict) else {}


@dataclass(frozen=True)
class ExecutionConfig:
    """Executor-level retry & validation semantics.

    Lives at ``agent_versions.config_json["execution"]``.
    """

    max_validation_retries: int = 0
    max_error_retries: int = 0
    output_validation_engine: Literal["jsonschema", "pydantic", "both"] = "both"

    @classmethod
    def from_agent(cls, agent: Any) -> ExecutionConfig:
        sub = _config_section(agent, "execution")
        return cls(
            max_validation_retries=int(sub.get("max_validation_retries") or 0),
            max_error_retries=int(sub.get("max_error_retries") or 0),
            output_validation_engine=sub.get("output_validation_engine") or "both",
        )


@dataclass(frozen=True)
class RuntimeConfig:
    """Runtime tooling/permissions surface.

    Lives at ``agent_versions.config_json["runtime"]``.
    """

    mcp_config_path: str | None = None
    allowed_tools: tuple[str, ...] = ()

    @classmethod
    def from_agent(cls, agent: Any) -> RuntimeConfig:
        sub = _config_section(agent, "runtime")
        return cls(
            mcp_config_path=sub.get("mcp_config_path"),
            allowed_tools=tuple(sub.get("allowed_tools") or ()),
        )


@dataclass(frozen=True)
class PythonAgentConfig:
    """Pydantic-ai / token backend dispatch metadata.

    Lives at ``agent_versions.config_json["python"]``.

    ``output_schema_path`` is included here because it's part of how
    the runtime locates the schema for the executor's validation loop.
    Long-term it should move to a binding (per the original plan); for
    now we keep the path-based contract.
    """

    agent_module: str | None = None
    deps_factory: str | None = None
    output_schema_path: str | None = None

    @classmethod
    def from_agent(cls, agent: Any) -> PythonAgentConfig:
        sub = _config_section(agent, "python")
        return cls(
            agent_module=sub.get("agent_module"),
            deps_factory=sub.get("deps_factory"),
            output_schema_path=sub.get("output_schema_path"),
        )


@dataclass(frozen=True)
class HttpValidatorConfig:
    """HTTP callback validator — POSTs output, expects {ok, error}.

    ``description`` is the human-readable constraint this validator
    enforces. It's rendered into the system prompt as a bullet under
    ``## Constraints`` so the model sees both the rule and knows it's
    enforced. Plan 22 — validators own their constraint text.
    """

    kind: Literal["http"] = "http"
    endpoint: str = ""
    timeout_seconds: int = 5
    description: str = ""


@dataclass(frozen=True)
class ScriptValidatorConfig:
    """Python script validator — runs operator-uploaded code in-process.

    The script (loaded from a versioned ``repo_resource`` of type
    ``'script'``) must define::

        def validate(output: str) -> dict:
            # return {"ok": True} or {"ok": False, "error": "..."}

    Resolved upstream by ``resolve_output_config`` so the runtime
    receives the source code directly and does not need DB access.

    ``description`` mirrors ``HttpValidatorConfig.description`` —
    human-readable constraint text rendered into the system prompt.
    """

    kind: Literal["script"] = "script"
    resource_id: str = ""
    resource_version_id: str | None = None
    source_code: str = ""
    description: str = ""


# Discriminated union — extend by adding a new dataclass + a kind
# branch in resolve_output_config + a dispatch in core/run/validation.
ValidatorConfig = HttpValidatorConfig | ScriptValidatorConfig


@dataclass(frozen=True)
class OutputConfig:
    """Resolved output validation surface for a single run.

    Two independent pieces (Plan 22 retired the floating ``rules[]``):

    - ``json_schema`` — Gate-1 structural validation. Sourced from the
      agent's ``slot='output_schema'`` resource binding. Its existence
      *is* the implicit jsonschema validator — never listed in
      ``validators``.
    - ``validators`` — explicit polymorphic post-hoc checkers from the
      bound validation contract. Each validator carries its own
      ``description`` (rendered into the prompt as a constraint bullet)
      and the actual check (HTTP endpoint, script resource, …). Today
      ``kind='http'`` and ``kind='script'``; new kinds add a dispatch
      branch in ``core/run/validation.validate_output`` with no DB
      migration.
    """

    json_schema: dict[str, Any] | None = None
    validators: tuple[ValidatorConfig, ...] = ()


def _normalize_validator_entries(
    store: Any, entries: list[dict]
) -> list[ValidatorConfig]:
    """Turn raw validator dicts (from inline config_json or a contract
    row) into typed :class:`ValidatorConfig`s.

    Script validators pre-load their source code so the runtime needs
    no DB access during dispatch. Unknown kinds are skipped silently —
    a newer writer may have introduced a kind this reader doesn't know.
    """
    out: list[ValidatorConfig] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        kind = entry.get("kind", "http")
        description = str(entry.get("description", "") or "")
        if kind == "http":
            out.append(
                HttpValidatorConfig(
                    kind="http",
                    endpoint=entry.get("endpoint", ""),
                    timeout_seconds=int(entry.get("timeout_seconds", 5)),
                    description=description,
                )
            )
        elif kind == "script":
            rid = entry.get("resource_id")
            if not rid:
                continue
            pinned = entry.get("pinned_version_id")
            ver = None
            if store is not None:
                try:
                    if pinned:
                        ver = store.get_repo_version(pinned)
                    else:
                        ver = store.get_active_repo_version(rid)
                except Exception:
                    ver = None
            source = ""
            if ver and store is not None:
                try:
                    blob = store.read_repo_blob(ver["id"], "")
                except Exception:
                    blob = None
                if blob:
                    text = blob.get("content_text") or ""
                    if not text:
                        raw_b = blob.get("content")
                        if isinstance(raw_b, (bytes, bytearray)):
                            try:
                                text = raw_b.decode("utf-8")
                            except UnicodeDecodeError:
                                text = ""
                    source = text
            out.append(
                ScriptValidatorConfig(
                    kind="script",
                    resource_id=rid,
                    resource_version_id=(ver or {}).get("id"),
                    source_code=source,
                    description=description,
                )
            )
    return out


def resolve_output_config(store: Any, agent: Any) -> OutputConfig:
    """Resolve the agent's output contract — single source of truth.

    Two independent reads:

    1. **Schema** — from the agent's active ``slot='output_schema'``
       prompt binding (resolved blob of the pinned-or-active version).
    2. **Validators** — inline ``config_json["output"].validators`` on
       the active agent_version (the only path after Plan 23).

    Either may be absent.
    """
    agent_id = getattr(agent, "id", None)
    schema: dict[str, Any] | None = None
    validators_raw: list[dict] = []

    if store is not None and agent_id:
        # --- schema from output_schema binding ---
        try:
            bindings = store.list_prompt_bindings(agent_id)
        except Exception:
            bindings = []
        binding = next((b for b in bindings if b.get("slot") == "output_schema"), None)
        if binding is not None:
            vid = binding.get("pinned_version_id")
            try:
                if vid:
                    ver = store.get_repo_version(vid)
                else:
                    ver = store.get_active_repo_version(binding["resource_id"])
            except Exception:
                ver = None
            if ver:
                try:
                    blob = store.read_repo_blob(ver["id"], "")
                except Exception:
                    blob = None
                if blob:
                    text = blob.get("content_text")
                    if not text:
                        raw_b = blob.get("content")
                        if isinstance(raw_b, (bytes, bytearray)):
                            try:
                                text = raw_b.decode("utf-8")
                            except UnicodeDecodeError:
                                text = None
                    if isinstance(text, str) and text:
                        try:
                            schema = _json.loads(text)
                        except (ValueError, TypeError):
                            schema = None

        # --- validators from inline config_json["output"].validators ---
        inline_section = _config_section(agent, "output")
        inline_list = inline_section.get("validators")
        if isinstance(inline_list, list):
            validators_raw = [v for v in inline_list if isinstance(v, dict)]

    validators = (
        _normalize_validator_entries(store, validators_raw) if validators_raw else []
    )

    return OutputConfig(
        json_schema=schema if isinstance(schema, dict) else None,
        validators=tuple(validators),
    )


def build_config_json_payload(agent: Any) -> dict[str, Any]:
    """Project an AgentDef into the structured ``config_json`` payload.

    Used by the backfill migration and by ``create_version`` going
    forward. Mirrors the runtime fallback so a freshly written
    ``config_json`` round-trips identically to the legacy reader.
    """
    exec_cfg = ExecutionConfig.from_agent(agent)
    runtime_cfg = RuntimeConfig.from_agent(agent)
    python_cfg = PythonAgentConfig.from_agent(agent)
    payload: dict[str, Any] = {
        "execution": {
            "max_validation_retries": exec_cfg.max_validation_retries,
            "max_error_retries": exec_cfg.max_error_retries,
            "output_validation_engine": exec_cfg.output_validation_engine,
        },
        "runtime": {
            "mcp_config_path": runtime_cfg.mcp_config_path,
            "allowed_tools": list(runtime_cfg.allowed_tools),
        },
        "python": {
            "agent_module": python_cfg.agent_module,
            "deps_factory": python_cfg.deps_factory,
            "output_schema_path": python_cfg.output_schema_path,
        },
    }
    return payload


__all__ = [
    "ExecutionConfig",
    "HttpValidatorConfig",
    "OutputConfig",
    "PythonAgentConfig",
    "RuntimeConfig",
    "ScriptValidatorConfig",
    "ValidatorConfig",
    "build_config_json_payload",
    "resolve_output_config",
]
