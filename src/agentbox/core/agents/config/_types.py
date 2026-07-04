"""Structured dataclasses for agent config sections.

Three logical buckets extracted from ``agent_versions.config_json``:

- ``ExecutionConfig`` — validation/retry semantics (executor-level).
- ``RuntimeConfig`` — runtime/tooling knobs (MCP config, allowed tools).
- ``PythonAgentConfig`` — pydantic-ai / token backend dispatch metadata.
- ``HttpValidatorConfig`` / ``ScriptValidatorConfig`` / ``OutputConfig`` —
  output-contract types used across execution and preview.
"""

from __future__ import annotations

import json as _json
from dataclasses import dataclass
from typing import Any, Literal, cast

from agentbox.core.data.payload_types import JsonSchemaDict
from agentbox.core.constants import ConfiguredValidationMode, ValidationMode
from agentbox.core.tools.canonical import CanonicalTool

_CONFIGURED_ENGINES = frozenset(
    {ValidationMode.JSONSCHEMA, ValidationMode.PYDANTIC, ValidationMode.BOTH}
)


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
    output_validation_engine: ConfiguredValidationMode = ValidationMode.BOTH

    @classmethod
    def from_agent(cls, agent: Any) -> ExecutionConfig:
        sub = _config_section(agent, "execution")
        raw_engine = sub.get("output_validation_engine") or ValidationMode.BOTH
        engine = cast(
            ConfiguredValidationMode,
            ValidationMode(raw_engine)
            if raw_engine in _CONFIGURED_ENGINES
            else ValidationMode.BOTH,
        )
        return cls(
            max_validation_retries=int(sub.get("max_validation_retries") or 0),
            max_error_retries=int(sub.get("max_error_retries") or 0),
            output_validation_engine=engine,
        )


@dataclass(frozen=True)
class RuntimeConfig:
    """Runtime tooling/permissions surface.

    Lives at ``agent_versions.config_json["runtime"]``.
    """

    mcp_config_path: str | None = None
    allowed_tools: tuple[CanonicalTool, ...] = ()

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
    Long-term it should move to a binding; for now we keep the
    path-based contract.
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
    enforced. Validators own their constraint text.
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

    Two independent pieces:

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

    json_schema: JsonSchemaDict | None = None
    validators: tuple[ValidatorConfig, ...] = ()
