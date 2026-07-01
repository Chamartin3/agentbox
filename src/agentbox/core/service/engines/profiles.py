"""Transitional runner-profile free-functions — delegate to EngineService.

The runner-profile logic now lives on ``EngineService`` (plan 091) over the
``RunnerProfileManager``. These free-functions are thin shims kept until the
remaining api/cli/test callers migrate to ``EngineService`` directly; the
``store`` parameter is ignored (EngineService self-wires to the same settings db).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agentbox.core.service.engines.service import EngineService, ProfileNotFound as _EngProfileNotFound

if TYPE_CHECKING:
    from agentbox.core.data import (
        RunnerProfile,
        RunnerProfileCreate,
        RunnerProfilePatch,
        RunnerProfileStats,
    )

# Preserve the historical import location for callers doing
# ``from ...engines.profiles import ProfileNotFound``.
ProfileNotFound = _EngProfileNotFound


def list_profiles(
    *,
    store: object,
    backend: str | None = None,
    provider: str | None = None,
    enabled: bool | None = None,
) -> list[RunnerProfile]:
    return EngineService().list_profiles(backend=backend, provider=provider, enabled=enabled)


def create_profile(data: RunnerProfileCreate, *, store: object) -> RunnerProfile:
    return EngineService().create_profile(data)


def get_profile(profile_id: str, *, store: object) -> RunnerProfile:
    return EngineService().get_profile(profile_id)


def update_profile(
    profile_id: str, patch: RunnerProfilePatch, *, store: object
) -> RunnerProfile:
    return EngineService().update_profile(profile_id, patch)


def delete_profile(profile_id: str, *, store: object) -> None:
    EngineService().delete_profile(profile_id)


def get_profile_stats(
    profile_id: str,
    *,
    store: object,
    since: str | None = None,
    until: str | None = None,
) -> RunnerProfileStats:
    return EngineService().get_profile_stats(profile_id, since=since, until=until)


# ── pass-through wrappers for CLI consumers ────────────────────────────────
def list_runner_profiles(
    store: object,
    *,
    backend: str | None = None,
    provider: str | None = None,
    enabled: bool | None = None,
) -> list[RunnerProfile]:
    return EngineService().list_profiles(backend=backend, provider=provider, enabled=enabled)


def get_runner_profile(store: object, profile_id: str) -> RunnerProfile | None:
    try:
        return EngineService().get_profile(profile_id)
    except ProfileNotFound:
        return None


def create_runner_profile(store: object, profile: RunnerProfileCreate) -> RunnerProfile:
    return EngineService().create_profile(profile)


def delete_runner_profile(store: object, profile_id: str) -> None:
    EngineService().delete_profile(profile_id)


def set_agent_runner_profile(
    store: object, agent_id: str, profile_id: str
) -> RunnerProfile:
    return EngineService().set_agent_runner_profile(agent_id, profile_id)


def get_agent_runner_profile(store: object, agent_id: str) -> RunnerProfile | None:
    return EngineService().get_agent_runner_profile(agent_id)


def runner_profile_stats(
    store: object,
    profile_id: str,
    *,
    since: str | None = None,
    until: str | None = None,
) -> RunnerProfileStats:
    return EngineService().get_profile_stats(profile_id, since=since, until=until)


def list_runner_profile_stats(
    store: object,
    *,
    since: str | None = None,
    until: str | None = None,
) -> list[RunnerProfileStats]:
    return EngineService().list_profile_stats(since=since, until=until)
