"""Base models, enum, and ABC for provider adapters.

A provider adapter knows how to discover models from one external LLM
service. ``HTTPProviderAdapter`` factors out the common pattern (fetch
JSON, optional bearer auth, parse, static fallback on failure) so each
concrete provider only declares its endpoint, response-shape parser,
and a curated fallback list.

Returned ``ProviderModel.id`` is the **short** model name (e.g.
``gpt-4o``), not the provider-prefixed form. The token-backend layer
prepends ``{provider}:`` when constructing pydantic-ai model strings.
CLI providers may return native CLI model ids instead (for example
``opencode/gpt-5``) because those backends pass model ids through verbatim.
"""

from __future__ import annotations

from agentbox.core.data.jsontypes import RawJson

import logging
import os
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, ClassVar, Protocol

import httpx
from pydantic import BaseModel, Field, computed_field


logger = logging.getLogger(__name__)


class Provider(str, Enum):  # noqa: UP042
    """Canonical identifiers for built-in providers."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    OPENROUTER = "openrouter"
    XAI = "xai"
    DEEPSEEK = "deepseek"
    OLLAMA = "ollama"
    CODEX = "codex"


class ProviderModel(BaseModel):
    """A single model available from a provider.

    ``id`` is the short name (``gpt-4o``). ``name`` is a human label
    (often equal to ``id``). The token backend prefixes ``id`` with
    ``{provider}:`` when building pydantic-ai model strings.
    """

    id: str
    name: str | None = None
    context_length: int | None = None
    input_modalities: list[str] = Field(default_factory=list)
    output_modalities: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class ProviderDescriptor(BaseModel):
    """Metadata describing a provider and its capabilities."""

    id: str
    label: str
    compatible_backends: list[str] = Field(default_factory=list)
    """Backend ids that can drive this provider. Empty means token-only (legacy).
    The single source of truth for backend compatibility."""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def backend(self) -> str:
        """The owning/primary backend — first of ``compatible_backends``.

        Derived (not stored) so there's one source of truth; kept on the
        wire for the runner-providers API + UI, which read ``backend``."""
        return self.compatible_backends[0] if self.compatible_backends else ""

    requires_api_key: bool
    supports_base_url: bool
    supports_model_listing: bool
    default_base_url: str | None = None
    default_api_key_env: str | None = None
    config_schema: RawJson = Field(default_factory=dict)
    discovered: bool = False
    """True when this provider only exists because a CLI (opencode) reported it
    at runtime, vs a preconfigured first-class adapter shipped with agentbox."""


class ProviderAdapter(Protocol):
    """Structural protocol every adapter satisfies."""

    @property
    def descriptor(self) -> ProviderDescriptor: ...

    async def list_models(self, config: Any) -> list[ProviderModel]: ...


class HTTPProviderAdapter(ABC):
    """Abstract base for HTTP-backed provider adapters.

    Subclasses set ``provider``, ``descriptor``, and ``static_models``,
    and implement ``_models_url`` and ``_parse_response``. ``list_models``
    handles fetch, auth, error recovery, and fallback uniformly.
    """

    provider: ClassVar[Provider]
    descriptor: ClassVar[ProviderDescriptor]
    static_models: ClassVar[list[str]] = []
    request_timeout_s: ClassVar[float] = 10.0

    @abstractmethod
    def _models_url(self, base_url: str) -> str:
        """Return the absolute URL whose GET returns the model list."""

    @abstractmethod
    def _parse_response(self, data: Any) -> list[ProviderModel]:
        """Translate the provider's JSON response into ProviderModels.

        Return short ids (no ``provider:`` prefix); the base class does
        not re-prefix.
        """

    def _auth_required_for_listing(self) -> bool:
        """Whether listing the /models endpoint requires a bearer token."""
        return self.descriptor.requires_api_key

    def _resolve(self, config: Any) -> tuple[str, str | None]:
        base_url = (
            getattr(config, "base_url", None) or self.descriptor.default_base_url
        ) or ""
        api_key_env = (
            getattr(config, "api_key_env", None) or self.descriptor.default_api_key_env
        )
        return base_url, api_key_env

    def _static(self) -> list[ProviderModel]:
        return [ProviderModel(id=m, name=m) for m in self.static_models]

    async def list_models(self, config: Any) -> list[ProviderModel]:
        base_url, api_key_env = self._resolve(config)
        api_key = os.environ.get(api_key_env) if api_key_env else None

        if self._auth_required_for_listing() and not api_key:
            logger.info(
                "%s: no api key, returning %d static models",
                self.provider.value,
                len(self.static_models),
            )
            return self._static()

        headers: dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    self._models_url(base_url),
                    headers=headers,
                    timeout=self.request_timeout_s,
                )
                resp.raise_for_status()
                data = resp.json()
            return self._parse_response(data)
        except Exception as exc:
            logger.warning(
                "%s: live model listing failed (%s); using static fallback",
                self.provider.value,
                exc,
            )
            return self._static()
