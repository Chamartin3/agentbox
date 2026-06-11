"""List repo-resources endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from agentbox.api.deps import get_store
from agentbox.core.constants import ResourceType
from agentbox.core.service import SessionStore
from agentbox.core.service import resources as resources_service

list_router = APIRouter(prefix="/api/repo-resources", tags=["repo-resources"])


@list_router.get("")
def list_resources(
    store: Annotated[SessionStore, Depends(get_store)],
    type: ResourceType | None = None,
    q: str | None = None,
    include_deleted: bool = False,
    limit: int = 50,
    offset: int = 0,
):
    return resources_service.list_resources(
        store=store,
        type=type,
        query=q,
        include_deleted=include_deleted,
        limit=limit,
        offset=offset,
    )
