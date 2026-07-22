"""DeepSeek provider adapter.

DeepSeek's API is OpenAI-compatible (Bearer ``DEEPSEEK_API_KEY``, ``/models``
endpoint), so this mirrors the xAI adapter. The token backend routes it via
``OpenAIProvider(base_url=...)`` at run time (see backends/token/run_direct).
"""

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


class DeepSeekAdapter(HTTPProviderAdapter):
    provider = Provider.DEEPSEEK
    descriptor = ProviderDescriptor(
        id=Provider.DEEPSEEK.value,
        label="DeepSeek",
        compatible_backends=["token"],
        requires_api_key=True,
        supports_base_url=True,
        supports_model_listing=True,
        default_base_url="https://api.deepseek.com",
        default_api_key_env="DEEPSEEK_API_KEY",
    )
    static_models = [
        "deepseek-chat",
        "deepseek-reasoner",
    ]

    def _models_url(self, base_url: str) -> str:
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
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    self._models_url(base_url),
                    headers=headers,
                    timeout=self.request_timeout_s,
                )
                resp.raise_for_status()
                return self._parse_response(resp.json())
        except Exception as exc:
            logger.warning("DeepSeek: model listing failed (%s); using static", exc)
            return self._static()
