"""Ollama provider adapter."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import urlparse, urlunparse

import httpx

from agentbox.core.config import SETTINGS
from agentbox.core.data.constants import BackendName
from agentbox.core.engines.providers.base import (
    HTTPProviderAdapter,
    Provider,
    ProviderDescriptor,
    ProviderModel,
)

logger = logging.getLogger(__name__)


_DEFAULT_CONTAINER_REWRITE = (
    "localhost=host.docker.internal,127.0.0.1=host.docker.internal"
)


def _running_in_container() -> bool:
    """Best-effort container detection — used to pick the default rewrite map."""
    if SETTINGS.in_container:
        return True
    return Path("/.dockerenv").exists()


def _parse_rewrite_map(raw: str) -> dict[str, str]:
    """Parse ``host1=host2,host3=host4`` into a hostname rewrite dict."""
    out: dict[str, str] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry or "=" not in entry:
            continue
        src, _, dst = entry.partition("=")
        src, dst = src.strip(), dst.strip()
        if src and dst:
            out[src] = dst
    return out


def _resolved_rewrite_map() -> dict[str, str]:
    """Hostname rewrite map applied to Ollama base URLs at lookup time.

    Resolution order:
      1. ``AGENTBOX_OLLAMA_URL_REWRITE`` env var (explicit override; empty
         string disables rewriting entirely).
      2. Container default (``localhost``/``127.0.0.1`` → ``host.docker.internal``)
         when running inside Docker.
      3. No rewrites.
    """
    override = SETTINGS.ollama_url_rewrite
    if override is not None:
        return _parse_rewrite_map(override)
    if _running_in_container():
        return _parse_rewrite_map(_DEFAULT_CONTAINER_REWRITE)
    return {}


def rewrite_ollama_url(url: str) -> str:
    """Apply the configured hostname rewrite to ``url``.

    Returns the input unchanged when no rewrite matches. The stored
    runner profile keeps the user-facing URL; only the runtime lookup
    is swapped so requests reach the host's Ollama service from inside
    the container.
    """
    rewrites = _resolved_rewrite_map()
    if not rewrites or not url:
        return url
    try:
        parsed = urlparse(url)
    except ValueError:
        return url
    host = parsed.hostname
    if host is None or host not in rewrites:
        return url
    new_host = rewrites[host]
    new_netloc = new_host
    if parsed.port is not None:
        new_netloc = f"{new_host}:{parsed.port}"
    if parsed.username:
        userinfo = parsed.username
        if parsed.password:
            userinfo += f":{parsed.password}"
        new_netloc = f"{userinfo}@{new_netloc}"
    return urlunparse(parsed._replace(netloc=new_netloc))


class OllamaAdapter(HTTPProviderAdapter):
    provider = Provider.OLLAMA
    descriptor = ProviderDescriptor(
        id=Provider.OLLAMA.value,
        label="Ollama",
        compatible_backends=[BackendName.TOKEN, BackendName.OPENCODE],
        requires_api_key=False,
        supports_base_url=True,
        supports_model_listing=True,
        default_base_url="http://localhost:11434",
        default_api_key_env=None,
    )
    static_models: ClassVar[list[str]] = []
    request_timeout_s = 5.0

    def _models_url(self, base_url: str) -> str:
        return f"{base_url}/api/tags"

    def _parse_response(self, data: Any) -> list[ProviderModel]:
        return [
            ProviderModel(id=item["name"], name=item["name"], raw=item)
            for item in data.get("models", [])
        ]

    async def list_models(self, config: Any) -> list[ProviderModel]:
        base_url, _api_key_env = self._resolve(config)
        effective_url = rewrite_ollama_url(base_url)
        if effective_url != base_url:
            logger.debug(
                "ollama: rewriting %s -> %s for in-container lookup",
                base_url,
                effective_url,
            )
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    self._models_url(effective_url),
                    timeout=self.request_timeout_s,
                )
                resp.raise_for_status()
                models = self._parse_response(resp.json())
        except Exception as exc:
            logger.warning("ollama: live local model listing failed (%s)", exc)
            return []

        if getattr(config, "backend", None) == BackendName.OPENCODE:
            return [
                ProviderModel(
                    id=f"ollama/{model.id}",
                    name=f"ollama/{model.id}",
                    raw=model.raw,
                )
                for model in models
            ]
        return models
