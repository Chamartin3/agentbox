"""Engine adapters, provider registry, credentials, and runner profiles.

**Import from this package, not its submodules.**

Public symbols are grouped by sub-domain:

Backends
--------
BackendAdapter, RenderedConfig, BackendRunResult,
get_backend, list_backends, backend_load_failure

Providers
---------
Provider, ProviderAdapter, HTTPProviderAdapter, ProviderDescriptor,
ProviderModel, get_provider, list_providers, list_models,
refresh_opencode_providers

Credentials
-----------
CredentialMethod, CredentialState, Method, get_credential,
list_credentials, register_credential, clear_credentials

Profiles
--------
EffectiveRunnerConfig, RunnerProfileResolver
"""

# -- Backends -----------------------------------------------------------------
from agentbox.core.data import BackendRunResult, RenderedConfig
from agentbox.core.engines.backends.base import BackendAdapter
from agentbox.core.engines.backends import get_backend, list_backends
from agentbox.core.engines.backends.registry import backend_load_failure

# -- Providers ----------------------------------------------------------------
from agentbox.core.engines.providers import (
    HTTPProviderAdapter,
    Provider,
    ProviderAdapter,
    ProviderDescriptor,
    ProviderModel,
    get_provider,
    list_providers,
)
from agentbox.core.engines.providers.registry import (
    list_models,
    refresh_opencode_providers,
)

# -- Credentials --------------------------------------------------------------
from agentbox.core.engines.credentials import (
    CredentialMethod,
    CredentialState,
    Method,
    clear as clear_credentials,
    get as get_credential,
    list_all as list_credentials,
    register as register_credential,
)

# -- Profiles -----------------------------------------------------------------
from agentbox.core.engines.profiles import EffectiveRunnerConfig, RunnerProfileResolver

__all__ = [
    # Backends
    "BackendAdapter",
    "BackendRunResult",
    "RenderedConfig",
    "backend_load_failure",
    "get_backend",
    "list_backends",
    # Providers
    "HTTPProviderAdapter",
    "Provider",
    "ProviderAdapter",
    "ProviderDescriptor",
    "ProviderModel",
    "get_provider",
    "list_providers",
    "list_models",
    "refresh_opencode_providers",
    # Credentials
    "CredentialMethod",
    "CredentialState",
    "Method",
    "clear_credentials",
    "get_credential",
    "list_credentials",
    "register_credential",
    # Profiles
    "EffectiveRunnerConfig",
    "RunnerProfileResolver",
]
