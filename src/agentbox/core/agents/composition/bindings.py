"""Agent prompt binding resolution.

Moved from ``core/workspaces/prep.py`` as part of the workspace-domain
refactoring (Plan 118).  Hydrates active prompt bindings for an agent
into resolver-ready dicts.
"""

from __future__ import annotations

import logging

from agentbox.core.data.payload_types import ResolvedPromptBinding
from agentbox.core.db import (
    AgentPromptResourceBindingManager,
    ResourceBlobManager,
    ResourceManager,
    ResourceVersionManager,
)

logger = logging.getLogger(__name__)


def resolve_agent_prompt_bindings(
    agent_prompt_resource_bindings: AgentPromptResourceBindingManager,
    resources: ResourceManager,
    resource_versions: ResourceVersionManager,
    resource_blobs: ResourceBlobManager,
    agent_id: str,
) -> list[ResolvedPromptBinding]:
    """Hydrate all active prompt bindings for an agent into resolver-ready dicts.

    Returns the same shape as ``_resolve_binding_for_prompt`` in the API
    route, so ``resolve_prompt`` can consume them directly.
    """
    bindings = agent_prompt_resource_bindings.list_for_agent(agent_id)
    if not bindings:
        return []

    resolved: list[ResolvedPromptBinding] = []
    for b in bindings:
        resource = resources.get_resource(b["resource_id"])
        if not resource:
            logger.warning(
                "workspace prep: prompt binding %s references missing resource %s — skipping",
                b["id"],
                b["resource_id"],
            )
            continue
        version_id = b.get("pinned_version_id")
        if version_id:
            version_id = str(version_id)
        if not version_id:
            active = resource_versions.get_active_version(b["resource_id"])
            if not active:
                logger.warning(
                    "workspace prep: resource %s has no active version — skipping prompt binding %s",
                    resource["slug"],
                    b["id"],
                )
                continue
            version_id = str(active["id"])
        version = resource_versions.get_version(version_id)
        if version is None:
            continue
        blobs = list(resource_blobs.iter_blobs(version_id))
        resolved.append(
            {
                "binding_id": b["id"],
                "marker": b.get("marker"),
                "slot": b.get("slot"),
                "attach_as_reference": bool(b.get("attach_as_reference")),
                "resource_id": b["resource_id"],
                "version_id": version_id,
                "content_hash": version["content_hash"],
                "type": resource["type"],
                "mode": b.get("mode"),
                "display_name": resource["display_name"],
                "required": bool(b.get("required", 1)),
                "blobs": blobs,
            }
        )
    return resolved
