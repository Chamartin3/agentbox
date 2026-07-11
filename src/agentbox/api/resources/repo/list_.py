"""List repo-resources endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from agentbox.api.deps import get_resource_service
from agentbox.core.data.constants import ResourceType
from agentbox.core.data.payload_types import ResourceListResult
from agentbox.core.service.resources import ResourceService

list_router = APIRouter(prefix="/api/repo-resources", tags=["repo-resources"])


@list_router.get("")
def list_resources(
    svc: Annotated[ResourceService, Depends(get_resource_service)],
    type: ResourceType | None = None,
    q: str | None = None,
    include_deleted: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> ResourceListResult:
    return svc.list_resources(
        type=type,
        query=q,
        include_deleted=include_deleted,
        limit=limit,
        offset=offset,
    )
