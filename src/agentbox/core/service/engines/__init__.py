"""Engines service layer — profiles, providers, backends, credentials."""

from agentbox.core.service.engines.profiles import (
    create_profile,
    create_runner_profile,
    delete_profile,
    get_agent_runner_profile,
    get_profile,
    get_runner_profile,
    list_profiles,
    set_agent_runner_profile,
)
from agentbox.core.service.engines.providers import (
    get_provider,
    list_providers,
)
from agentbox.core.service.engines.service import (
    EngineService,
    ProfileNotFound,
)

# ── Data models (types the service methods accept / return) ───────────────
# The facade exposes Service objects + data models only — operations live as
# methods on ``EngineService`` (e.g. ``EngineService().list_backend_names()``),
# never as re-exported free functions.
from agentbox.core.engines import (
    CredentialMethod,
    CredentialState,
    Method,
    ProviderDescriptor,
    ProviderModel,
)

__all__ = [
    "create_profile",
    "create_runner_profile",
    "CredentialMethod",
    "CredentialState",
    "delete_profile",
    "EngineService",
    "get_agent_runner_profile",
    "get_profile",
    "get_provider",
    "get_runner_profile",
    "list_profiles",
    "list_providers",
    "Method",
    "ProfileNotFound",
    "ProviderDescriptor",
    "ProviderModel",
    "set_agent_runner_profile",
]
