"""Structured dataclasses for agent config sections + config_json builder.

Three logical buckets extracted from ``agent_versions.config_json``:

- ``ExecutionConfig`` — validation/retry semantics (executor-level).
- ``RuntimeConfig`` — runtime/tooling knobs (MCP config, allowed tools).
- ``PythonAgentConfig`` — pydantic-ai / token backend dispatch metadata.

``config_json`` is the sole source of truth — there is no legacy
``agent.runner`` fallback.
"""

from __future__ import annotations

import json as _json
from dataclasses import dataclass
from typing import Any

from agentbox.core.data.payload_types import ConfigJsonPayload
from agentbox.core.data import CanonicalTool


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

    @classmethod
    def from_agent(cls, agent: Any) -> ExecutionConfig:
        sub = _config_section(agent, "execution")
        return cls(
            max_validation_retries=int(sub.get("max_validation_retries") or 0),
            max_error_retries=int(sub.get("max_error_retries") or 0),
        )


@dataclass(frozen=True)
class RuntimeConfig:
    """Runtime tooling/permissions surface.

    Lives at ``agent_versions.config_json["runtime"]``.
    """

    mcp_config_path: str | None = None
    allowed_tools: tuple[CanonicalTool, ...] = ()
    forbidden_tools: tuple[CanonicalTool, ...] = ()

    @classmethod
    def from_agent(cls, agent: Any) -> RuntimeConfig:
        sub = _config_section(agent, "runtime")
        return cls(
            mcp_config_path=sub.get("mcp_config_path"),
            allowed_tools=tuple(sub.get("allowed_tools") or ()),
            forbidden_tools=tuple(sub.get("forbidden_tools") or ()),
        )


@dataclass(frozen=True)
class PythonAgentConfig:
    """Pydantic-ai / token backend dispatch metadata.

    Lives at ``agent_versions.config_json["python"]``.

    ``output_schema_path`` is the *import/authoring* boundary: it is written
    when importing from TOML or when an API caller supplies a path. At runtime
    the executor resolves the schema from the DB binding (``slot='output_schema'``
    on ``agent_prompt_resource_bindings``) rather than reading the file.
    The path field remains here for backward-compat serialisation.
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


def build_config_json_payload(agent: Any) -> ConfigJsonPayload:
    """Project an AgentDef into the structured ``config_json`` payload.

    Used by the backfill migration and by ``create_version`` going
    forward. Mirrors the runtime fallback so a freshly written
    ``config_json`` round-trips identically to the legacy reader.
    """
    exec_cfg = ExecutionConfig.from_agent(agent)
    runtime_cfg = RuntimeConfig.from_agent(agent)
    python_cfg = PythonAgentConfig.from_agent(agent)
    payload: ConfigJsonPayload = {
        "execution": {
            "max_validation_retries": exec_cfg.max_validation_retries,
            "max_error_retries": exec_cfg.max_error_retries,
        },
        "runtime": {
            "mcp_config_path": runtime_cfg.mcp_config_path,
            "allowed_tools": list(runtime_cfg.allowed_tools),
            "forbidden_tools": list(runtime_cfg.forbidden_tools),
        },
        "python": {
            "agent_module": python_cfg.agent_module,
            "deps_factory": python_cfg.deps_factory,
            "output_schema_path": python_cfg.output_schema_path,
        },
    }
    return payload
