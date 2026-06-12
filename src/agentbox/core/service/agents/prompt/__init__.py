"""Agent config patching + validation — extracted from __init__.py per C10.

Import from ``service.agents`` (the package), never from this module directly.
"""

from agentbox.core.service.agents.prompt.patch import (
    AgentServiceError as AgentServiceError,
    decode_config_json as decode_config_json,
    patch_agent_config as patch_agent_config,
)
from agentbox.core.service.agents.prompt.validation import (
    get_agent_validation as get_agent_validation,
    normalize_validator_entries as normalize_validator_entries,
    put_agent_validation as put_agent_validation,
)

__all__ = [
    "AgentServiceError",
    "decode_config_json",
    "get_agent_validation",
    "normalize_validator_entries",
    "patch_agent_config",
    "put_agent_validation",
]
