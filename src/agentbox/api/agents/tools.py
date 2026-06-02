"""Read-only endpoints to inspect the SharedToolRegistry (Plan 19)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from agentbox.core.tools import SharedToolRegistry

router = APIRouter(prefix="/api/agent_tools", tags=["agent-tools-discovery"])


def _spec_to_dict(spec) -> dict:
    return {
        "name": spec.name,
        "description": spec.description,
        "capability": spec.capability,
        "tags": list(spec.tags),
        "input_schema": spec.input_model.model_json_schema(),
        "output_schema": spec.output_model.model_json_schema(),
    }


@router.get("")
def list_agent_tools(tag: str | None = None):
    specs = SharedToolRegistry.all()
    if tag:
        specs = [s for s in specs if tag in s.tags]
    return {"items": [_spec_to_dict(s) for s in specs]}


@router.get("/{tool_name:path}")
def get_agent_tool(tool_name: str):
    spec = SharedToolRegistry.get(tool_name)
    if spec is None:
        raise HTTPException(404, f"Tool {tool_name!r} not found in registry")
    return _spec_to_dict(spec)
