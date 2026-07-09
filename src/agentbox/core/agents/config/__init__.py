"""Structured accessors for agent semantics stored in ``config_json``.

These dataclasses split agent config into three logical buckets:

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
    PythonAgentConfig as PythonAgentConfig,
    RuntimeConfig as RuntimeConfig,
)
from agentbox.core.agents.config._helpers import (
    build_config_json_payload as build_config_json_payload,
)
from agentbox.core.data.composition import (
    HttpValidatorConfig as HttpValidatorConfig,
    ScriptValidatorConfig as ScriptValidatorConfig,
    ValidatorConfig as ValidatorConfig,
)

__all__ = [
    "ExecutionConfig",
    "HttpValidatorConfig",
    "PythonAgentConfig",
    "RuntimeConfig",
    "ScriptValidatorConfig",
    "ValidatorConfig",
    "build_config_json_payload",
]
