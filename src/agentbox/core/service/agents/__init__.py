"""Shared agent-resolution service used by both REST and MCP surfaces.

The DB (``agent_versions`` / ``active_agent_versions``) is the single
source of truth. There is no manifest fallback.

Import from this package — the submodules are internal.
"""

from agentbox.core.agents.composition.versioning.drift import (
    _build_snapshot as build_agent_snapshot,  # noqa: F401  -- re-exported via core.service
)

from agentbox.core.service.agents.crud import (
    get_agent_detail as get_agent_detail,
    list_agents_enriched as list_agents_enriched,
    list_all_agents as list_all_agents,
    resolve_agent as resolve_agent,
)
from agentbox.core.service.agents.prompt import (
    AgentServiceError as AgentServiceError,
    decode_config_json as decode_config_json,
    get_agent_validation as get_agent_validation,
    normalize_validator_entries as normalize_validator_entries,
    patch_agent_config as patch_agent_config,
    put_agent_validation as put_agent_validation,
)
from agentbox.core.service.agents.versions import (
    AgentAlreadyExists as AgentAlreadyExists,
    AgentNotFound as AgentNotFound,
    DuplicateVersionFile as DuplicateVersionFile,
    VersionFileNotFound as VersionFileNotFound,
    VersionNotFound as VersionNotFound,
    VersionNotDraft as VersionNotDraft,
    create_agent_record as create_agent_record,
    delete_version_file as delete_version_file,
    require_agent_exists as require_agent_exists,
    upload_version_file as upload_version_file,
)
