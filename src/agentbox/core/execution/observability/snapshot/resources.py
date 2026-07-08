"""Build resource-snapshot entries for a run row."""

from __future__ import annotations

import logging
from typing import Any

from agentbox.core.db import WorkspaceHostEnvGrantManager
from agentbox.core.tools.capabilities import (
    CAPABILITIES as _HOST_ENV_CAPABILITIES,
)
from agentbox.core.workspaces.tooling.servers import resolve_workspace_host_env_helper

logger = logging.getLogger(__name__)


def resolve_host_env_grants(
    workspace_host_env_grants: "WorkspaceHostEnvGrantManager",
    workspace_id: str | None,
) -> dict[str, Any] | None:
    """Return the workspace's non-default host-env grants, or ``None``.

    The returned dict maps capability names to their grant configurations.
    Each grant config is a TypedDict-shaped dict with capability-specific settings.
    """
    if not workspace_id:
        return None
    try:
        resolved_he = resolve_workspace_host_env_helper(
            workspace_host_env_grants, workspace_id
        )
        grants = resolved_he.get("grants") or {}
        non_default = {
            k for k, v in _HOST_ENV_CAPABILITIES.items() if not v.default_granted
        }
        if grants.keys() & non_default:
            return grants
    except Exception:
        logger.exception(
            "executor: host-env grant resolution failed for workspace %r",
            workspace_id,
        )
    return None


# Alias used by the public observability facade.
build_resource_snapshot_entries = resolve_host_env_grants


__all__ = ["build_resource_snapshot_entries", "resolve_host_env_grants"]
