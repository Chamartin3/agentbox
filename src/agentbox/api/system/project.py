"""/api/project — typed wrappers over the DB-backed project config.

Project-level settings (formerly in ``agentbox.toml``) live in the
``settings`` table. ``/api/settings/{section}`` exposes the raw
key/value section; this module adds typed CRUD for the structured
``project_mcp_servers`` section so the UI can manage individual
servers without hand-rolling JSON.

For ``project_shared_assets`` and ``project_runtime`` (flat scalars),
continue using ``PATCH /api/settings/{section}``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from agentbox.api.deps import get_store
from agentbox.core.data import McpServerSpec

router = APIRouter(prefix="/api/project", tags=["project"])


@router.get("/mcp-servers")
def list_project_mcp_servers(store=Depends(get_store)) -> dict:
    servers = store.get_project_mcp_servers()
    return {"servers": [s.model_dump(mode="json") for s in servers]}


@router.put("/mcp-servers/{name}")
def upsert_project_mcp_server(
    name: str, spec: McpServerSpec, store=Depends(get_store)
) -> dict:
    if spec.name != name:
        spec = spec.model_copy(update={"name": name})
    store.set_project_mcp_server(spec)
    return spec.model_dump(mode="json")


@router.delete("/mcp-servers/{name}")
def delete_project_mcp_server(name: str, store=Depends(get_store)) -> dict:
    existing = {s.name for s in store.get_project_mcp_servers()}
    if name not in existing:
        raise HTTPException(status_code=404, detail=f"unknown mcp server: {name!r}")
    store.delete_project_mcp_server(name)
    return {"deleted": name}
