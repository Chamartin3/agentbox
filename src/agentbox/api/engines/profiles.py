"""/runner-profiles endpoints — CRUD, agent binding, stats.

Transport-only: parses queries, calls
:mod:`agentbox.core.service.engines.service.EngineService`, maps domain errors
to HTTP.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from agentbox.api._pagination import PaginatedEnvelope, paginate_list
from agentbox.api.deps import get_engine_service
from agentbox.core.service import (
    RunnerProfile,
    RunnerProfileCreate,
    RunnerProfilePatch,
    RunnerProfileStats,
)
from agentbox.core.service.engines.profile_validation import InvalidProfile
from agentbox.core.service.engines.service import EngineService, ProfileNotFound

router = APIRouter(prefix="/api/runner-profiles", tags=["runner-profiles"])


@router.get("")
def list_runner_profiles(
    response: Response,
    backend: str | None = None,
    provider: str | None = None,
    enabled: bool | None = None,
    q: str | None = None,
    sort: str | None = None,
    order: str = "asc",
    limit: int = 50,
    offset: int = 0,
    paginated: bool = False,
    engine_svc: EngineService = Depends(get_engine_service),
) -> list[RunnerProfile] | PaginatedEnvelope:
    """List runner profiles with optional filters.

    Pass ``paginated=true`` (or any of ``q/sort/order/offset``) to get the
    envelope ``{items, total, offset, limit, has_more}``. Otherwise returns
    a plain list for backward compatibility.
    """
    profiles = engine_svc.list_profiles(
        backend=backend, provider=provider, enabled=enabled
    )

    if not paginated and not any([q, sort, offset]):
        return profiles

    items_as_dicts = [p.model_dump() for p in profiles]
    page = paginate_list(
        items_as_dicts,
        q=q,
        q_fields=("id", "name", "backend", "provider", "model"),
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )
    response.headers["X-Total-Count"] = str(page["total"])
    return page


@router.post("", status_code=201)
def create_runner_profile(
    data: RunnerProfileCreate,
    engine_svc: EngineService = Depends(get_engine_service),
) -> RunnerProfile:
    try:
        return engine_svc.create_profile(data)
    except InvalidProfile as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/{profile_id}")
def get_runner_profile(
    profile_id: str,
    engine_svc: EngineService = Depends(get_engine_service),
) -> RunnerProfile:
    try:
        return engine_svc.get_profile(profile_id)
    except ProfileNotFound as exc:
        raise HTTPException(404, str(exc)) from exc


@router.patch("/{profile_id}")
def update_runner_profile(
    profile_id: str,
    patch: RunnerProfilePatch,
    engine_svc: EngineService = Depends(get_engine_service),
) -> RunnerProfile:
    try:
        return engine_svc.update_profile(profile_id, patch)
    except ProfileNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except InvalidProfile as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete("/{profile_id}")
def delete_runner_profile(
    profile_id: str,
    engine_svc: EngineService = Depends(get_engine_service),
) -> None:
    try:
        engine_svc.delete_profile(profile_id)
    except ProfileNotFound as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/{profile_id}/stats")
def get_runner_profile_stats(
    profile_id: str,
    since: str | None = None,
    until: str | None = None,
    engine_svc: EngineService = Depends(get_engine_service),
) -> RunnerProfileStats:
    try:
        return engine_svc.get_profile_stats(
            profile_id, since=since, until=until
        )
    except ProfileNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
