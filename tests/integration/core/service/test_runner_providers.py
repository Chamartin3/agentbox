"""Tests for ``core.service.runner_providers`` — discovery + model listing.

Validates provider filtering, error translation (httpx → domain errors),
and the async model-listing path.
"""

from __future__ import annotations

from pathlib import Path
import httpx
import pytest
from agentbox.core.engines.providers.base import ProviderDescriptor
from agentbox.core.db.database import Database
from agentbox.core.service.engines import (
    InvalidProviderRequest,
    ProviderAuthFailed,
    ProviderNotFound,
    ProviderUpstreamError,
    list_provider_models,
    list_runner_providers,
)


@pytest.fixture
def store(tmp_path: Path) -> Database:
    return Database(tmp_path / "agentbox.sqlite")


class _FakeProvider:
    def __init__(self, compatible_backends: list[str] | None = None) -> None:
        self.descriptor = ProviderDescriptor(
            id="mock",
            label="Mock Provider",
            backend="mock",
            compatible_backends=compatible_backends or ["mock"],
            requires_api_key=False,
            supports_base_url=True,
            supports_model_listing=True,
            default_base_url="https://mock.ai/v1",
        )


def _patch_providers(
    monkeypatch,
    *,
    compat: list[str] | None = None,
) -> _FakeProvider:
    provider = _FakeProvider(compat)

    def _list_providers():
        return [provider.descriptor]

    def _get_provider(name: str) -> _FakeProvider | None:
        if name == "mock":
            return provider
        return None

    monkeypatch.setattr(
        "agentbox.core.service.engines.list_providers", _list_providers
    )
    monkeypatch.setattr(
        "agentbox.core.service.engines.get_provider", _get_provider
    )
    return provider


# ── list_runner_providers ──────────────────────────────────────────────


def test_list_runner_providers_no_filter(monkeypatch) -> None:
    _patch_providers(monkeypatch)
    providers = list_runner_providers()
    assert len(providers) == 1
    assert providers[0].id == "mock"


def test_list_runner_providers_backend_filter_matches(monkeypatch) -> None:
    _patch_providers(monkeypatch, compat=["mock"])
    providers = list_runner_providers(backend="mock")
    assert len(providers) == 1


def test_list_runner_providers_backend_filter_excludes(monkeypatch) -> None:
    _patch_providers(monkeypatch, compat=["other"])
    providers = list_runner_providers(backend="mock")
    assert len(providers) == 0


# ── list_provider_models ───────────────────────────────────────────────


async def test_list_provider_models_unknown_provider(store: Database) -> None:
    with pytest.raises(ProviderNotFound):
        await list_provider_models("nonexistent", runner_profiles=store.runner_profiles)


async def test_list_provider_models_incompatible_backend(
    store: Database, monkeypatch
) -> None:
    _patch_providers(monkeypatch, compat=["other"])
    with pytest.raises(InvalidProviderRequest, match="not compatible"):
        await list_provider_models("mock", runner_profiles=store.runner_profiles, backend="mock")


async def test_list_provider_models_missing_profile(
    store: Database, monkeypatch
) -> None:
    _patch_providers(monkeypatch, compat=["mock"])
    with pytest.raises(InvalidProviderRequest, match="Runner profile not found"):
        await list_provider_models("mock", runner_profiles=store.runner_profiles, profile_id="missing")


async def test_list_provider_models_auth_failed(
    store: Database, monkeypatch
) -> None:
    _patch_providers(monkeypatch, compat=["mock"])

    async def _raise_auth(*args, **kwargs):
        raise httpx.HTTPStatusError(
            "unauthorized",
            request=httpx.Request("GET", "https://mock.ai"),
            response=httpx.Response(401),
        )

    monkeypatch.setattr(
        "agentbox.core.service.engines.registry_list_models",
        _raise_auth,
    )
    with pytest.raises(ProviderAuthFailed) as exc_info:
        await list_provider_models("mock", runner_profiles=store.runner_profiles, backend="mock")
    assert exc_info.value.status_code == 401


async def test_list_provider_models_upstream_error(
    store: Database, monkeypatch
) -> None:
    _patch_providers(monkeypatch, compat=["mock"])

    async def _raise_500(*args, **kwargs):
        raise httpx.HTTPStatusError(
            "server error",
            request=httpx.Request("GET", "https://mock.ai"),
            response=httpx.Response(500),
        )

    monkeypatch.setattr(
        "agentbox.core.service.engines.registry_list_models",
        _raise_500,
    )
    with pytest.raises(ProviderUpstreamError):
        await list_provider_models("mock", runner_profiles=store.runner_profiles, backend="mock")


async def test_list_provider_models_request_error(
    store: Database, monkeypatch
) -> None:
    _patch_providers(monkeypatch, compat=["mock"])

    async def _raise_request_error(*args, **kwargs):
        raise httpx.RequestError("connection refused")

    monkeypatch.setattr(
        "agentbox.core.service.engines.registry_list_models",
        _raise_request_error,
    )
    with pytest.raises(ProviderUpstreamError):
        await list_provider_models("mock", runner_profiles=store.runner_profiles, backend="mock")


async def test_list_provider_models_value_error_from_registry(
    store: Database, monkeypatch
) -> None:
    _patch_providers(monkeypatch, compat=["mock"])

    async def _raise_value_error(*args, **kwargs):
        raise ValueError("registry rejected config")

    monkeypatch.setattr(
        "agentbox.core.service.engines.registry_list_models",
        _raise_value_error,
    )
    with pytest.raises(InvalidProviderRequest):
        await list_provider_models("mock", runner_profiles=store.runner_profiles, backend="mock")
