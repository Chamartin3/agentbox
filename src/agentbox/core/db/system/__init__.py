"""System domain — host-env profiles, MCP discovery, settings, credentials.

One file per table (entity + manager together). The manager is the public
surface; the entity is importable directly for cross-domain FK references.
"""
from __future__ import annotations

from agentbox.core.db.system.host_env_call import (
    HostEnvCallLog,
    HostEnvCallLogManager,
)
from agentbox.core.db.system.host_env_profile import (
    HostEnvProfile,
    HostEnvProfileManager,
)
from agentbox.core.db.system.managed_credential import (
    ManagedCredential,
    ManagedCredentialManager,
)
from agentbox.core.db.system.mcp_discovery_cache import (
    McpToolDiscoveryCache,
    McpToolDiscoveryCacheManager,
)
from agentbox.core.db.system.setting import (
    Setting,
    SettingManager,
)

__all__ = [
    # managed_credential entity + manager
    "ManagedCredential",
    "ManagedCredentialManager",
    # host_env_call entity + manager
    "HostEnvCallLog",
    "HostEnvCallLogManager",
    # host_env_profile entity + manager
    "HostEnvProfile",
    "HostEnvProfileManager",
    # mcp_discovery_cache entity + manager
    "McpToolDiscoveryCache",
    "McpToolDiscoveryCacheManager",
    # setting entity + manager
    "Setting",
    "SettingManager",
]
