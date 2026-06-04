"""xAI provider adapter."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from agentbox.core.engines.providers.base import (
    HTTPProviderAdapter,
    Provider,
    ProviderDescriptor,
    ProviderModel,
)

logger = logging.getLogger(__name__)


class XAIAdapter(HTTPProviderAdapter):
    provider = Provider.XAI
    descriptor = ProviderDescriptor(
        id=Provider.XAI.value,
        label="xAI",
        backend="token",
        compatible_backends=["token"],
        requires_api_key=True,
        supports_base_url=True,
        supports_model_listing=True,
        default_base_url="https://api.x.ai/v1",
        default_api_key_env="XAI_API_KEY",
    )
    static_models = [
        "grok-3",
        "grok-3-mini",
        "grok-2",
        "grok-2-mini",
        "grok-beta",
        "grok-vision-beta",
    ]

    def _models_url(self, base_url: str) -> str:
        return f"{base_url}/language-models"

    def _fallback_url(self, base_url: str) -> str:
        return f"{base_url}/models"

    def _parse_response(self, data: Any) -> list[ProviderModel]:
        return [
            ProviderModel(id=item["id"], name=item.get("name") or item["id"], raw=item)
            for item in data.get("data", [])
        ]

    async def list_models(self, config: Any) -> list[ProviderModel]:
        base_url, api_key_env = self._resolve(config)
        api_key = os.environ.get(api_key_env) if api_key_env else None
        if not api_key:
            return self._static()

        headers = {"Authorization": f"Bearer {api_key}"}
        for url in (self._models_url(base_url), self._fallback_url(base_url)):
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        url, headers=headers, timeout=self.request_timeout_s
                    )
                    resp.raise_for_status()
                    return self._parse_response(resp.json())
            except Exception as exc:
                logger.debug("xAI: %s failed (%s)", url, exc)
                continue
        logger.warning("xAI: both endpoints failed; using static fallback")
        return self._static()
