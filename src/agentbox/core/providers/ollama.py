"""Ollama provider adapter."""

from __future__ import annotations

from typing import Any

from agentbox.core.providers.base import (
    HTTPProviderAdapter,
    Provider,
    ProviderDescriptor,
    ProviderModel,
)


class OllamaAdapter(HTTPProviderAdapter):
    provider = Provider.OLLAMA
    descriptor = ProviderDescriptor(
        id=Provider.OLLAMA.value,
        label="Ollama",
        backend="token",
        compatible_backends=["token", "opencode"],
        requires_api_key=False,
        supports_base_url=True,
        supports_model_listing=True,
        default_base_url="http://localhost:11434",
        default_api_key_env=None,
    )
    static_models = [
        "llama3.2",
        "llama3.1",
        "llama3",
        "qwen2.5",
        "qwen2.5-coder",
        "mistral",
        "mixtral",
        "codellama",
        "phi3",
        "gemma2",
    ]
    request_timeout_s = 5.0

    def _models_url(self, base_url: str) -> str:
        return f"{base_url}/api/tags"

    def _parse_response(self, data: Any) -> list[ProviderModel]:
        return [
            ProviderModel(id=item["name"], name=item["name"], raw=item)
            for item in data.get("models", [])
        ]
