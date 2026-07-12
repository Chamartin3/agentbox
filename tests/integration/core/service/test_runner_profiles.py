"""Tests for ``core.service.runner_profiles`` — CRUD + validation.

Covers per-field validators (backend, provider, base_url, api_key_env,
headers, backend↔provider compat), create/update/delete/get/list flows,
and the store-layer integration.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import agentbox.core.service.engines as pv
from agentbox.core.data import (
    RunnerProfileCreate,
    RunnerProfilePatch,
)
from agentbox.core.db.database import Database
from agentbox.core.engines.providers.base import ProviderDescriptor as PD
from agentbox.core.service.engines import (
    EngineService,
    InvalidProfile,
    ProfileNotFound,
    validate_create,
    validate_patch,
)


@pytest.fixture
def store(tmp_path: Path) -> Database:
    return Database(tmp_path / "agentbox.sqlite")


# ── Fake plugin / provider surfaces ────────────────────────────────────


class _FakeBackend:
    name = "mock"


class _FakeProvider:
    def __init__(self, compatible_backends: list[str] | None = None) -> None:
        self.descriptor = PD(
            id="mock",
            label="Mock Provider",
            backend="mock",
            compatible_backends=compatible_backends or ["mock"],
            requires_api_key=False,
            supports_base_url=True,
            supports_model_listing=True,
            default_base_url="https://mock.ai/v1",
        )


def _patch_backends(monkeypatch, *, fail_load: str | None = None) -> None:
    assert hasattr(pv, "resolve_engine_by_name"), (
        "profile_validation contract changed — update _patch_backends"
    )
    assert hasattr(pv, "list_engines"), (
        "profile_validation contract changed — update _patch_backends"
    )
    assert hasattr(pv, "engine_load_failure"), (
        "profile_validation contract changed — update _patch_backends"
    )

    def _get_backend(name: str) -> _FakeBackend:
        if name == "mock":
            return _FakeBackend()
        raise KeyError(name)

    def _backends() -> dict[str, _FakeBackend]:
        return {"mock": _FakeBackend()}

    def _backend_load_failure(name: str) -> str | None:
        if name == fail_load:
            return "Missing dep: mock"
        if name == "mock":
            return None
        return None

    monkeypatch.setattr(
        "agentbox.core.service.engines.resolve_engine_by_name",
        _get_backend,
    )
    monkeypatch.setattr(
        "agentbox.core.service.engines.list_engines", _backends
    )
    monkeypatch.setattr(
        "agentbox.core.service.engines.engine_load_failure",
        _backend_load_failure,
    )


def _patch_providers(monkeypatch, *, compat: list[str] | None = None) -> None:
    provider = _FakeProvider(compat)

    def _list_providers_impl():
        return [provider.descriptor]

    def _get_provider(name: str) -> _FakeProvider | None:
        if name == "mock":
            return provider
        return None

    monkeypatch.setattr(
        "agentbox.core.service.engines.list_providers", _list_providers_impl
    )
    monkeypatch.setattr(
        "agentbox.core.service.engines.get_provider", _get_provider
    )


# ── validate_create ────────────────────────────────────────────────────


def test_validate_create_rejects_bad_backend(monkeypatch) -> None:
    _patch_backends(monkeypatch)
    data = RunnerProfileCreate(name="test", backend="bogus")
    with pytest.raises(InvalidProfile, match="unknown backend"):
        validate_create(data)


def test_validate_create_rejects_backend_load_failure(monkeypatch) -> None:
    _patch_backends(monkeypatch, fail_load="broken")
    data = RunnerProfileCreate(name="test", backend="broken")
    with pytest.raises(InvalidProfile, match="declared but failed to load"):
        validate_create(data)


def test_validate_create_rejects_unknown_provider(monkeypatch) -> None:
    _patch_backends(monkeypatch)
    _patch_providers(monkeypatch)
    data = RunnerProfileCreate(name="test", backend="mock", provider="bogus")
    with pytest.raises(InvalidProfile, match="unknown provider"):
        validate_create(data)


def test_validate_create_rejects_bad_base_url(monkeypatch) -> None:
    _patch_backends(monkeypatch)
    data = RunnerProfileCreate(name="test", backend="mock", base_url="ftp://evil")
    with pytest.raises(InvalidProfile, match="base_url must start with"):
        validate_create(data)


def test_validate_create_rejects_secret_looking_api_key(monkeypatch) -> None:
    _patch_backends(monkeypatch)
    data = RunnerProfileCreate(name="test", backend="mock", api_key_env="sk-abc123")
    with pytest.raises(InvalidProfile, match="looks like a secret value"):
        validate_create(data)


def test_validate_create_rejects_lowercase_api_key_env(monkeypatch) -> None:
    _patch_backends(monkeypatch)
    data = RunnerProfileCreate(name="test", backend="mock", api_key_env="api_key")
    with pytest.raises(InvalidProfile, match="must be a valid env var name"):
        validate_create(data)


def test_validate_create_rejects_oversized_api_key_env(monkeypatch) -> None:
    _patch_backends(monkeypatch)
    data = RunnerProfileCreate(
        name="test",
        backend="mock",
        api_key_env="A" * 65,
    )
    with pytest.raises(InvalidProfile, match="looks like a secret value"):
        validate_create(data)


def test_validate_create_rejects_incompatible_backend_provider(monkeypatch) -> None:
    _patch_backends(monkeypatch)
    _patch_providers(monkeypatch, compat=["other"])
    data = RunnerProfileCreate(name="test", backend="mock", provider="mock")
    with pytest.raises(InvalidProfile, match="not compatible"):
        validate_create(data)


def test_validate_create_rejects_authorization_header(monkeypatch) -> None:
    _patch_backends(monkeypatch)
    data = RunnerProfileCreate(
        name="test",
        backend="mock",
        headers={"Authorization": "Bearer x"},
    )
    with pytest.raises(InvalidProfile, match="headers cannot include Authorization"):
        validate_create(data)


# ── validate_patch ─────────────────────────────────────────────────────


def test_validate_patch_uses_current_backend_for_compat(monkeypatch) -> None:
    """Patching only the provider uses the existing backend for compat check."""
    _patch_backends(monkeypatch)
    _patch_providers(monkeypatch, compat=["other"])
    patch = RunnerProfilePatch(provider="mock")
    with pytest.raises(InvalidProfile, match="not compatible"):
        validate_patch(patch, current_backend="mock")


# ── CRUD round-trip ────────────────────────────────────────────────────


def test_create_profile_round_trip(store: Database, monkeypatch) -> None:
    _patch_backends(monkeypatch)
    data = RunnerProfileCreate(name="test", backend="mock")
    profile = EngineService().create_profile(data)
    assert profile.name == "test"
    assert profile.backend == "mock"
    assert profile.id


def test_get_profile_raises_profile_not_found(store: Database) -> None:
    with pytest.raises(ProfileNotFound):
        EngineService().get_profile("nonexistent")


def test_update_profile_raises_profile_not_found(store: Database) -> None:
    with pytest.raises(ProfileNotFound):
        EngineService().update_profile("nonexistent", RunnerProfilePatch(name="x"))


def test_delete_profile_raises_profile_not_found(store: Database) -> None:
    with pytest.raises(ProfileNotFound):
        EngineService().delete_profile("nonexistent")


def test_get_profile_stats_raises_profile_not_found(store: Database) -> None:
    with pytest.raises(ProfileNotFound):
        EngineService().get_profile_stats("nonexistent")


def test_list_profiles_returns_empty_list(store: Database) -> None:
    assert EngineService().list_profiles() == []


def test_list_profiles_filters_by_backend(store: Database, monkeypatch) -> None:
    _patch_backends(monkeypatch)
    EngineService().create_profile(RunnerProfileCreate(name="a", backend="mock"))
    EngineService().create_profile(RunnerProfileCreate(name="b", backend="mock"))
    # Filtering by a backend that exists but has no matches
    result = EngineService().list_profiles(backend="other")
    assert len(result) == 0
    # All profiles
    all_profiles = EngineService().list_profiles()
    assert len(all_profiles) == 2
