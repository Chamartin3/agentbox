"""OpenAI provider adapter."""

from __future__ import annotations

from typing import Any

from agentbox.core.data.constants import BackendName
from agentbox.core.engines.providers.base import (
    HTTPProviderAdapter,
    Provider,
    ProviderDescriptor,
    ProviderModel,
)


class OpenAIAdapter(HTTPProviderAdapter):
    provider = Provider.OPENAI
    descriptor = ProviderDescriptor(
        id=Provider.OPENAI.value,
        label="OpenAI",
        backend=BackendName.TOKEN,
        compatible_backends=[BackendName.TOKEN],
        requires_api_key=True,
        supports_base_url=True,
        supports_model_listing=True,
        default_base_url="https://api.openai.com/v1",
        default_api_key_env="OPENAI_API_KEY",
    )
    static_models = [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "gpt-4",
        "gpt-3.5-turbo",
        "o1",
        "o1-mini",
        "o3",
        "o3-mini",
    ]

    def _models_url(self, base_url: str) -> str:
        return f"{base_url}/models"

    # OpenAI's /v1/models returns *every* model on the account — embeddings,
    # whisper, tts, dall-e, moderation, deprecated davinci/babbage, etc.
    # Keep only chat-completable model families.
    _CHAT_PREFIXES = ("gpt-", "o1", "o3", "o4", "chatgpt-")
    _EXCLUDE_SUBSTRINGS = (
        "embedding",
        "whisper",
        "tts",
        "dall-e",
        "moderation",
        "audio",
        "image",
        "realtime",
        "transcribe",
        "search",
    )

    def _is_chat_model(self, model_id: str) -> bool:
        mid = model_id.lower()
        if not any(mid.startswith(p) for p in self._CHAT_PREFIXES):
            return False
        return not any(s in mid for s in self._EXCLUDE_SUBSTRINGS)

    def _parse_response(self, data: Any) -> list[ProviderModel]:
        return [
            ProviderModel(id=item["id"], name=item["id"], raw=item)
            for item in data.get("data", [])
            if self._is_chat_model(item.get("id", ""))
        ]
