"""Delete repo-resource endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from agentbox.api.deps import get_resource_service
from agentbox.core.service.resources import ResourceNotFound, ResourceService
from agentbox.api.resources.repo._models import _raise_not_found

delete_router = APIRouter(prefix="/api/repo-resources", tags=["repo-resources"])


@delete_router.delete("/{resource_id}", status_code=204)
def soft_delete_resource(
    resource_id: str,
    svc: Annotated[ResourceService, Depends(get_resource_service)],
    reason: Annotated[str, Query(min_length=3)],
) -> Response:
    try:
        svc.soft_delete_resource(resource_id, reason=reason)
    except ResourceNotFound:
        _raise_not_found()
    return Response(status_code=204)
