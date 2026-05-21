"""Anthropic provider adapter."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from agentbox.core.agent.providers.base import (
    HTTPProviderAdapter,
    Provider,
    ProviderDescriptor,
    ProviderModel,
)

logger = logging.getLogger(__name__)


class AnthropicAdapter(HTTPProviderAdapter):
    provider = Provider.ANTHROPIC
    descriptor = ProviderDescriptor(
        id=Provider.ANTHROPIC.value,
        label="Anthropic",
        backend="token",
        compatible_backends=["token", "claude_code"],
        requires_api_key=True,
        supports_base_url=True,
        supports_model_listing=True,
        default_base_url="https://api.anthropic.com/v1",
        default_api_key_env="ANTHROPIC_API_KEY",
    )
    static_models = [
        "claude-opus-4-7",
        "claude-sonnet-4-6",
        "claude-haiku-4-5",
        "claude-3-5-sonnet-latest",
        "claude-3-5-haiku-latest",
        "claude-3-opus-latest",
    ]

    def _models_url(self, base_url: str) -> str:
        return f"{base_url}/models"

    def _parse_response(self, data: Any) -> list[ProviderModel]:
        return [
            ProviderModel(
                id=item["id"],
                name=item.get("display_name") or item["id"],
                raw=item,
            )
            for item in data.get("data", [])
        ]

    async def list_models(self, config: Any) -> list[ProviderModel]:
        base_url, api_key_env = self._resolve(config)
        api_key = os.environ.get(api_key_env) if api_key_env else None
        if not api_key:
            return self._static()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    self._models_url(base_url),
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                    },
                    timeout=self.request_timeout_s,
                )
                resp.raise_for_status()
                return self._parse_response(resp.json())
        except Exception as exc:
            logger.warning(
                "anthropic: live listing failed (%s); using static fallback", exc
            )
            return self._static()
