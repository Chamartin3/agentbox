"""Service layer for runner-profile CRUD.

Per-field validation lives in
:mod:`agentbox.core.service.engines.profile_validation` — call it from
there directly. This module raises :class:`ProfileNotFound` for lookup
misses; validation rejections raise
:class:`~.profile_validation.InvalidProfile`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agentbox.core.service.engines import profile_validation

if TYPE_CHECKING:
    from agentbox.core.db import (
        RunnerProfile,
        RunnerProfileCreate,
        RunnerProfilePatch,
        RunnerProfileStats,
        SessionStore,
    )


class ProfileNotFound(LookupError):
    def __init__(self, profile_id: str) -> None:
        super().__init__(f"runner profile not found: {profile_id!r}")
        self.profile_id = profile_id


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def list_profiles(
    *,
    store: SessionStore,
    backend: str | None = None,
    provider: str | None = None,
    enabled: bool | None = None,
) -> list[RunnerProfile]:
    return store.list_runner_profiles(backend=backend, provider=provider, enabled=enabled)


def create_profile(
    data: RunnerProfileCreate, *, store: SessionStore
) -> RunnerProfile:
    profile_validation.validate_create(data)
    return store.create_runner_profile(data)


def get_profile(profile_id: str, *, store: SessionStore) -> RunnerProfile:
    profile = store.get_runner_profile(profile_id)
    if profile is None:
        raise ProfileNotFound(profile_id)
    return profile


def update_profile(
    profile_id: str, patch: RunnerProfilePatch, *, store: SessionStore
) -> RunnerProfile:
    current = store.get_runner_profile(profile_id)
    if current is None:
        raise ProfileNotFound(profile_id)
    profile_validation.validate_patch(patch, current_backend=current.backend)
    return store.update_runner_profile(profile_id, patch)


def delete_profile(profile_id: str, *, store: SessionStore) -> None:
    if store.get_runner_profile(profile_id) is None:
        raise ProfileNotFound(profile_id)
    store.delete_runner_profile(profile_id)


def get_profile_stats(
    profile_id: str,
    *,
    store: SessionStore,
    since: str | None = None,
    until: str | None = None,
) -> RunnerProfileStats:
    if store.get_runner_profile(profile_id) is None:
        raise ProfileNotFound(profile_id)
    return store.runner_profile_stats(profile_id, since=since, until=until)


# ---------------------------------------------------------------------------
# Pass-through wrappers for CLI consumers
# ---------------------------------------------------------------------------


def list_runner_profiles(
    store: SessionStore,
    *,
    backend: str | None = None,
    provider: str | None = None,
    enabled: bool | None = None,
) -> list[RunnerProfile]:
    return store.list_runner_profiles(backend=backend, provider=provider, enabled=enabled)


def get_runner_profile(store: SessionStore, profile_id: str) -> RunnerProfile | None:
    return store.get_runner_profile(profile_id)


def create_runner_profile(
    store: SessionStore, profile: RunnerProfileCreate
) -> RunnerProfile:
    return store.create_runner_profile(profile)


def delete_runner_profile(store: SessionStore, profile_id: str) -> None:
    store.delete_runner_profile(profile_id)


def set_agent_runner_profile(
    store: SessionStore, agent_id: str, profile_id: str
) -> RunnerProfile:
    return store.set_agent_runner_profile(agent_id, profile_id)


def get_agent_runner_profile(
    store: SessionStore, agent_id: str
) -> RunnerProfile | None:
    return store.get_agent_runner_profile(agent_id)


def runner_profile_stats(
    store: SessionStore,
    profile_id: str,
    *,
    since: str | None = None,
    until: str | None = None,
) -> RunnerProfileStats:
    return store.runner_profile_stats(profile_id, since=since, until=until)


def list_runner_profile_stats(
    store: SessionStore,
    *,
    since: str | None = None,
    until: str | None = None,
) -> list[RunnerProfileStats]:
    return store.list_runner_profile_stats(since=since, until=until)
