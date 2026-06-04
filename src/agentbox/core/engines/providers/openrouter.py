"""OpenRouter provider adapter."""

from __future__ import annotations

from typing import Any

from agentbox.core.engines.providers.base import (
    HTTPProviderAdapter,
    Provider,
    ProviderDescriptor,
    ProviderModel,
)


class OpenRouterAdapter(HTTPProviderAdapter):
    provider = Provider.OPENROUTER
    descriptor = ProviderDescriptor(
        id=Provider.OPENROUTER.value,
        label="OpenRouter",
        backend="token",
        compatible_backends=["token", "opencode"],
        requires_api_key=False,
        supports_base_url=True,
        supports_model_listing=True,
        default_base_url="https://openrouter.ai/api/v1",
        default_api_key_env="OPENROUTER_API_KEY",
    )
    static_models = [
        "openai/gpt-4o",
        "openai/gpt-4o-mini",
        "anthropic/claude-3.5-sonnet",
        "anthropic/claude-3.5-haiku",
        "google/gemini-2.0-flash-001",
        "meta-llama/llama-3.3-70b-instruct",
        "qwen/qwen-2.5-72b-instruct",
        "mistralai/mistral-large",
    ]

    def _auth_required_for_listing(self) -> bool:
        return False

    def _models_url(self, base_url: str) -> str:
        return f"{base_url}/models"

    def _parse_response(self, data: Any) -> list[ProviderModel]:
        return [
            ProviderModel(
                id=item["id"],
                name=item.get("name") or item["id"],
                context_length=item.get("context_length"),
                raw=item,
            )
            for item in data.get("data", [])
        ]
