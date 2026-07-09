"""Resolver and builder functions for agent config."""

from __future__ import annotations

from typing import Any

from agentbox.core.data.payload_types import ConfigJsonPayload
from agentbox.core.agents.config._types import (
    ExecutionConfig,
    PythonAgentConfig,
    RuntimeConfig,
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
