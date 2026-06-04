"""Provider registry for LLM model discovery and configuration.

This package provides descriptors and model listing for HTTP-based LLM
providers (OpenAI, OpenRouter, xAI, Ollama, etc.). It does not execute
agents — that responsibility remains with the token backend.
"""

from agentbox.core.agents.providers.base import (
    HTTPProviderAdapter,
    Provider,
    ProviderAdapter,
    ProviderDescriptor,
    ProviderModel,
)
from agentbox.core.agents.providers.registry import get_provider, list_providers

__all__ = [
    "HTTPProviderAdapter",
    "Provider",
    "ProviderAdapter",
    "ProviderDescriptor",
    "ProviderModel",
    "get_provider",
    "list_providers",
]
