"""Structured accessors for agent semantics stored in ``config_json``.

Phase 2 of the runner-DB-as-source-of-truth refactor. These dataclasses
split what was historically jammed into ``AgentDef.runner`` into three
logical buckets:

- ``ExecutionConfig`` — validation/retry semantics (executor-level).
- ``RuntimeConfig`` — runtime/tooling knobs (MCP config, allowed tools).
- ``PythonAgentConfig`` — pydantic-ai / token backend dispatch metadata
  (module, deps factory, output schema path).

The values live in ``agent_versions.config_json`` under sub-keys
``execution`` / ``runtime`` / ``python``. ``config_json`` is the sole
source of truth — there is no legacy ``agent.runner`` fallback.
"""

from agentbox.core.agents.config._types import (
    ExecutionConfig as ExecutionConfig,
    HttpValidatorConfig as HttpValidatorConfig,
    OutputConfig as OutputConfig,
    PythonAgentConfig as PythonAgentConfig,
    RuntimeConfig as RuntimeConfig,
    ScriptValidatorConfig as ScriptValidatorConfig,
    ValidatorConfig as ValidatorConfig,
)
from agentbox.core.agents.config._helpers import (
    build_config_json_payload as build_config_json_payload,
    resolve_output_config as resolve_output_config,
)

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
