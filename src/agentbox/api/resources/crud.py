"""Shared resources CRUD + versioning endpoints."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from agentbox.api.deps import get_store
from agentbox.core.data import SharedResourceRecord


def _mark_deprecated(response: Response) -> None:
    """Inject RFC 8594 Deprecation headers pointing to /api/repo-resources.

    The legacy /api/resources surface is preserved for one release so
    consumers can migrate; every response advertises the successor.
    """
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = '</api/repo-resources>; rel="successor-version"'


router = APIRouter(
    prefix="/api/resources",
    tags=["resources"],
    dependencies=[Depends(_mark_deprecated)],
)

# Valid resource kinds
VALID_KINDS = Literal[
    "output_schema",
    "input_schema",
    "user_template",
    "system_fragment",
    "reference",
    "mcp_server",
    "skill",
]


class SharedResourceResponse(BaseModel):
    """Pydantic model for SharedResourceRecord serialization."""

    id: str
    version: int
    kind: str
    name: str
    sha256: str
    created_at: str
    description: str | None = None
    content: str | None = None
    config_json: str | None = None
    is_active: bool = False
    author: str | None = None
    changelog: str | None = None
    tags: list[str] = Field(default_factory=list)

    @classmethod
    def from_record(cls, record: SharedResourceRecord) -> SharedResourceResponse:
        """Convert SharedResourceRecord to response model."""
        return cls(
            id=record.id,
            version=record.version,
            kind=record.kind,
            name=record.name,
            sha256=record.sha256,
            created_at=record.created_at,
            description=record.description,
            content=record.content,
            config_json=record.config_json,
            is_active=record.is_active,
            author=record.author,
            changelog=record.changelog,
            tags=list(record.tags),
        )


class CreateResourceRequest(BaseModel):
    """Request body for POST /api/resources."""

    id: str
    kind: str
    name: str
    description: str | None = None
    content: str | None = None
    config_json: str | None = None
    author: str
    changelog: str
    tags: list[str] | None = None
    activate: bool = True


class CreateResourceVersionRequest(BaseModel):
    """Request body for POST /api/resources/{id}/versions."""

    content: str | None = None
    config_json: str | None = None
    author: str
    changelog: str
    activate: bool = False
    name: str | None = None
    description: str | None = None
    tags: list[str] | None = None


class ActivateVersionRequest(BaseModel):
    """Request body for POST /api/resources/{id}/activate."""

    version: int


class PaginatedResourcesResponse(BaseModel):
    """Response for paginated resource list."""

    items: list[SharedResourceResponse]
    total: int | None = None


# ---------------------------------------------------------------------------
# List resources
# ---------------------------------------------------------------------------


@router.get("")
def list_resources(
    kind: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> PaginatedResourcesResponse:
    """List active resources, optionally filtered by kind and search text.

    Returns only the active version of each resource.
    """
    store = get_store()
    resources = store.list_resources(kind=kind, q=q, limit=limit, offset=offset)
    total = store.count_active_resources(kind=kind, q=q)
    return PaginatedResourcesResponse(
        items=[SharedResourceResponse.from_record(r) for r in resources],
        total=total,
    )


# ---------------------------------------------------------------------------
# Get single resource
# ---------------------------------------------------------------------------


@router.get("/{id}")
def get_resource(id: str) -> SharedResourceResponse:
    """Get the active version of a resource.

    Returns 404 if no active version exists.
    """
    store = get_store()
    resource = store.get_active_resource(id)
    if resource is None:
        raise HTTPException(404, f"Resource {id!r} not found")
    return SharedResourceResponse.from_record(resource)


# ---------------------------------------------------------------------------
# Create resource
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
def create_resource(body: CreateResourceRequest) -> SharedResourceResponse:
    """Create a new resource (version 1) and optionally activate it.

    Returns 409 if resource id already exists.
    """
    # Validate kind
    if body.kind not in [
        "output_schema",
        "input_schema",
        "user_template",
        "system_fragment",
        "reference",
        "mcp_server",
        "skill",
    ]:
        raise HTTPException(
            400, f"Invalid kind {body.kind!r}; must be one of the valid resource kinds"
        )

    # Validate required fields
    if not body.author or not body.author.strip():
        raise HTTPException(400, "author is required and must be non-empty")
    if not body.changelog or len(body.changelog) < 3:
        raise HTTPException(
            400, "changelog is required and must be at least 3 characters"
        )

    store = get_store()
    try:
        resource = store.create_resource(
            id=body.id,
            kind=body.kind,
            name=body.name,
            description=body.description,
            content=body.content,
            config_json=body.config_json,
            author=body.author,
            changelog=body.changelog,
            tags=body.tags,
            activate=body.activate,
        )
    except ValueError as exc:
        # Duplicate ID or other validation error
        if "already exists" in str(exc).lower():
            raise HTTPException(409, f"Resource {body.id!r} already exists") from exc
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        # Catch IntegrityError (unique constraint) and other DB errors
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            raise HTTPException(409, f"Resource {body.id!r} already exists") from exc
        raise HTTPException(400, str(exc)) from exc

    return SharedResourceResponse.from_record(resource)


# ---------------------------------------------------------------------------
# List resource versions
# ---------------------------------------------------------------------------


@router.get("/{id}/versions")
def list_resource_versions(
    id: str, limit: int = 50, offset: int = 0
) -> PaginatedResourcesResponse:
    """List all versions of a resource."""
    store = get_store()
    versions = store.list_resource_versions(id, limit=limit, offset=offset)
    return PaginatedResourcesResponse(
        items=[SharedResourceResponse.from_record(v) for v in versions],
        total=None,
    )


# ---------------------------------------------------------------------------
# Create resource version
# ---------------------------------------------------------------------------


@router.post("/{id}/versions", status_code=201)
def create_resource_version(
    id: str, body: CreateResourceVersionRequest
) -> SharedResourceResponse:
    """Create a new version of an existing resource.

    Returns 404 if resource id doesn't exist.
    """
    # Validate required fields
    if not body.author or not body.author.strip():
        raise HTTPException(400, "author is required and must be non-empty")
    if not body.changelog or len(body.changelog) < 3:
        raise HTTPException(
            400, "changelog is required and must be at least 3 characters"
        )

    store = get_store()
    fields_to_update = {}
    if body.name is not None:
        fields_to_update["name"] = body.name
    if body.description is not None:
        fields_to_update["description"] = body.description
    if body.tags is not None:
        fields_to_update["tags"] = body.tags

    try:
        resource = store.create_resource_version(
            id,
            content=body.content,
            config_json=body.config_json,
            author=body.author,
            changelog=body.changelog,
            activate=body.activate,
            **fields_to_update,
        )
    except ValueError as exc:
        # Resource not found
        if "not found" in str(exc).lower():
            raise HTTPException(404, str(exc)) from exc
        raise HTTPException(400, str(exc)) from exc

    return SharedResourceResponse.from_record(resource)


# ---------------------------------------------------------------------------
# Activate version
# ---------------------------------------------------------------------------


@router.post("/{id}/activate", status_code=200)
def activate_resource_version(
    id: str, body: ActivateVersionRequest
) -> SharedResourceResponse:
    """Atomically activate a specific version and deactivate others.

    Returns 404 if resource/version doesn't exist.
    """
    store = get_store()
    try:
        resource = store.activate_resource(id, body.version)
    except ValueError as exc:
        # Version not found
        raise HTTPException(404, str(exc)) from exc

    return SharedResourceResponse.from_record(resource)
