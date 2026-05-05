"""Google Gemini provider adapter."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from agentbox.core.providers.base import (
    HTTPProviderAdapter,
    Provider,
    ProviderDescriptor,
    ProviderModel,
)

logger = logging.getLogger(__name__)


class GoogleAdapter(HTTPProviderAdapter):
    """Google Generative Language (Gemini) provider.

    Auth: ``?key=<API_KEY>`` query param (not bearer). Model ids in the
    REST API look like ``models/gemini-2.0-flash``; we strip the
    ``models/`` prefix so the short id matches pydantic-ai's expected
    ``google:<model>`` form.
    """

    provider = Provider.GOOGLE
    descriptor = ProviderDescriptor(
        id=Provider.GOOGLE.value,
        label="Google Gemini",
        backend="token",
        compatible_backends=["token"],
        requires_api_key=True,
        supports_base_url=True,
        supports_model_listing=True,
        default_base_url="https://generativelanguage.googleapis.com/v1beta",
        default_api_key_env="GOOGLE_API_KEY",
    )
    static_models = [
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
        "gemini-1.5-flash-8b",
    ]

    def _models_url(self, base_url: str) -> str:
        return f"{base_url}/models"

    def _parse_response(self, data: Any) -> list[ProviderModel]:
        out: list[ProviderModel] = []
        for item in data.get("models", []):
            raw_id = item.get("name", "")
            short = raw_id.removeprefix("models/") if raw_id.startswith("models/") else raw_id
            if not short:
                continue
            out.append(
                ProviderModel(
                    id=short,
                    name=item.get("displayName") or short,
                    context_length=item.get("inputTokenLimit"),
                    raw=item,
                )
            )
        return out

    async def list_models(self, config: Any) -> list[ProviderModel]:
        base_url, api_key_env = self._resolve(config)
        api_key = os.environ.get(api_key_env) if api_key_env else None
        if not api_key:
            return self._static()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    self._models_url(base_url),
                    params={"key": api_key},
                    timeout=self.request_timeout_s,
                )
                resp.raise_for_status()
                return self._parse_response(resp.json())
        except Exception as exc:
            logger.warning("google: live listing failed (%s); using static fallback", exc)
            return self._static()
