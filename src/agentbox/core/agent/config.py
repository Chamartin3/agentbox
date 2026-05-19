"""Structured accessors for agent semantics stored in ``config_json``.

Phase 2 of the runner-DB-as-source-of-truth refactor (see
``runner-db-source-of-truth.md``). These dataclasses split what was
historically jammed into ``AgentDef.runner`` into three logical buckets:

- ``ExecutionConfig`` — validation/retry semantics (executor-level).
- ``RuntimeConfig`` — runtime/tooling knobs (MCP config, allowed tools).
- ``PythonAgentConfig`` — pydantic-ai / token backend dispatch metadata
  (module, deps factory, output schema path).

The values live in ``agent_versions.config_json`` under sub-keys
``execution`` / ``runtime`` / ``python``. Each ``from_agent()`` factory
reads those keys first and falls back to the legacy ``agent.runner``
fields so unmigrated agents keep working transparently. The backfill
migration (``backfill_agent_config_json``) copies the legacy values
into the new sub-dicts so the fallback never triggers in steady state.

Runner-level config (backend, model, timeout, provider, extra_args)
stays out of here entirely — that's ``EffectiveRunnerConfig`` resolved
from ``runner_profiles`` by ``RunnerProfileResolver``.
"""

from __future__ import annotations

import json as _json
from dataclasses import dataclass
from typing import Any, Literal


def _runner_attr(agent: Any, name: str, default: Any = None) -> Any:
    runner = getattr(agent, "runner", None)
    if runner is None:
        return default
    val = getattr(runner, name, default)
    return val if val is not None else default


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

    Lives at ``agent_versions.config_json["execution"]``. Falls back to
    ``agent.runner`` for unmigrated agents.
    """

    max_validation_retries: int = 0
    max_error_retries: int = 0
    output_validation_engine: Literal["jsonschema", "pydantic", "both"] = "both"

    @classmethod
    def from_agent(cls, agent: Any) -> ExecutionConfig:
        sub = _config_section(agent, "execution")
        return cls(
            max_validation_retries=int(
                sub.get("max_validation_retries")
                if sub.get("max_validation_retries") is not None
                else _runner_attr(agent, "max_validation_retries", 0)
            ),
            max_error_retries=int(
                sub.get("max_error_retries")
                if sub.get("max_error_retries") is not None
                else _runner_attr(agent, "max_error_retries", 0)
            ),
            output_validation_engine=(
                sub.get("output_validation_engine")
                or _runner_attr(agent, "output_validation_engine", "both")
            ),
        )


@dataclass(frozen=True)
class RuntimeConfig:
    """Runtime tooling/permissions surface.

    Lives at ``agent_versions.config_json["runtime"]``. Falls back to
    ``agent.runner`` for unmigrated agents.
    """

    mcp_config_path: str | None = None
    allowed_tools: tuple[str, ...] = ()

    @classmethod
    def from_agent(cls, agent: Any) -> RuntimeConfig:
        sub = _config_section(agent, "runtime")
        tools = sub.get("allowed_tools")
        if tools is None:
            tools = _runner_attr(agent, "allowed_tools", []) or []
        return cls(
            mcp_config_path=(
                sub.get("mcp_config_path")
                if "mcp_config_path" in sub
                else _runner_attr(agent, "mcp_config_path", None)
            ),
            allowed_tools=tuple(tools),
        )


@dataclass(frozen=True)
class PythonAgentConfig:
    """Pydantic-ai / token backend dispatch metadata.

    Lives at ``agent_versions.config_json["python"]``. Falls back to
    ``agent.runner`` for unmigrated agents.

    ``output_schema_path`` is included here because it's part of how
    the runtime locates the schema for the executor's validation loop.
    Long-term it should move to a binding (per the original plan); for
    now we keep the path-based contract.

    ``output_model`` is a dotted import path (``"pkg.module:ClassName"``)
    pointing at the canonical Pydantic output class. When set, the
    executor's validator imports the class and runs
    ``ClassName.model_validate_json(...)`` — catching cross-field
    ``@model_validator`` rules that ``model_json_schema()`` cannot
    express. The schema embedded in the system prompt is also derived
    from the same class so the prompt and the validator can't drift.
    """

    agent_module: str | None = None
    deps_factory: str | None = None
    output_schema_path: str | None = None
    output_model: str | None = None

    @classmethod
    def from_agent(cls, agent: Any) -> PythonAgentConfig:
        sub = _config_section(agent, "python")
        return cls(
            agent_module=(
                sub.get("agent_module")
                if "agent_module" in sub
                else _runner_attr(agent, "agent_module", None)
            ),
            deps_factory=(
                sub.get("deps_factory")
                if "deps_factory" in sub
                else _runner_attr(agent, "deps_factory", None)
            ),
            output_schema_path=(
                sub.get("output_schema_path")
                if "output_schema_path" in sub
                else _runner_attr(agent, "output_schema_path", None)
            ),
            output_model=(
                sub.get("output_model")
                if "output_model" in sub
                else _runner_attr(agent, "output_model", None)
            ),
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
            "output_model": python_cfg.output_model,
        },
    }
    return payload


__all__ = [
    "ExecutionConfig",
    "PythonAgentConfig",
    "RuntimeConfig",
    "build_config_json_payload",
]
