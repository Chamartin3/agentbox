"""Agent service package.

``AgentService`` (``.service``) is the public surface for the agent domain —
import it from ``agentbox.core.service`` (the facade). The submodules here
(``crud``, ``versions``, ``prompt``, ``lifecycle``, ``admin``) are internal
implementation that ``AgentService`` delegates to during the migration off
``SessionStore``; do not import their functions directly.

The free-function re-exports below are all transitional — every one is a
method on ``AgentService`` now, but these callers haven't moved yet:

- ``resolve_agent`` / ``list_all_agents`` — cli (deferred to the CLI
  restructure) + not-yet-migrated service-layer modules (execution/workspaces).
- ``get_agent_validation`` / ``put_agent_validation`` — cli ``agent check``.
- ``upload_version_file`` / ``delete_version_file`` / ``require_agent_exists``
  — cli ``agent files`` / ``agent version``.
- ``build_agent_snapshot`` — re-exported through the facade; internal helper.
- The agent-domain exceptions — part of the Service's error contract.

Each collapses to AgentService-only as its caller migrates. The fully-dead
re-exports (get_agent_detail, list_agents_enriched, create_agent_record,
patch_agent_config, decode_config_json, normalize_validator_entries) were
removed — api/mcp use the Service methods; the functions live on in their
submodules only as AgentService's internal delegates.
"""

from agentbox.core.agents import (
    build_agent_snapshot as build_agent_snapshot,  # noqa: F401  -- re-exported via core.service
)
from agentbox.core.service.agents.crud import (
    get_agent_detail as get_agent_detail,
    list_agents_enriched as list_agents_enriched,
    list_all_agents as list_all_agents,
    resolve_agent as resolve_agent,
)
from agentbox.core.service.agents.prompt_patch import (
    AgentServiceError as AgentServiceError,
)
from agentbox.core.service.agents.prompt_validation import (
    get_agent_validation as get_agent_validation,
    put_agent_validation as put_agent_validation,
)
from agentbox.core.service.agents.versions import (
    AgentAlreadyExists as AgentAlreadyExists,
    AgentNotFound as AgentNotFound,
    DuplicateVersionFile as DuplicateVersionFile,
    VersionFileNotFound as VersionFileNotFound,
    VersionNotFound as VersionNotFound,
    VersionNotDraft as VersionNotDraft,
    delete_version_file as delete_version_file,
    require_agent_exists as require_agent_exists,
    upload_version_file as upload_version_file,
)
from agentbox.core.agents import (
    PreviewError as PreviewError,
)
