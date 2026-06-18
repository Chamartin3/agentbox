"""Alias router: ``/api/providers/**`` → ``/api/runner-profiles/**``.

The Settings UI uses the new name ("providers"). Server keeps the old prefix
as the canonical implementation; this router 307-redirects so request bodies
and methods are preserved.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

router = APIRouter(tags=["providers-alias"])


@router.api_route(
    "/api/providers",
    methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    include_in_schema=False,
)
@router.api_route(
    "/api/providers/{rest:path}",
    methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    include_in_schema=False,
)
def providers_alias(request: Request, rest: str = "") -> RedirectResponse:
    suffix = f"/{rest}" if rest else ""
    qs = request.url.query
    target = f"/api/runner-profiles{suffix}" + (f"?{qs}" if qs else "")
    # 307 preserves method + body
    return RedirectResponse(target, status_code=307)


@router.api_route(
    "/api/provider-backends",
    methods=["GET"],
    include_in_schema=False,
)
@router.api_route(
    "/api/provider-backends/{rest:path}",
    methods=["GET"],
    include_in_schema=False,
)
def provider_backends_alias(request: Request, rest: str = "") -> RedirectResponse:
    suffix = f"/{rest}" if rest else ""
    qs = request.url.query
    target = f"/api/runner-providers{suffix}" + (f"?{qs}" if qs else "")
    return RedirectResponse(target, status_code=307)
