"""Read-only endpoints for the canonical tool catalog.

Returns the union of built-in canonical tools (``BUILTIN_TOOLS``) and
runtime-registered shared agent tools (``SharedToolRegistry``).
Authorization is handled by ``/api/agents/{id}/tool_grants``; this
endpoint is pure discovery.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from agentbox.core.tools import BUILTIN_TOOLS, SharedToolRegistry

router = APIRouter(prefix="/api/agent_tools", tags=["agent-tools-discovery"])


def _builtin_to_dict(spec) -> dict:
    return {
        "name": spec.name,
        "description": spec.description,
        "capability": spec.capability,
        "params": list(spec.params),
        "kind": "builtin",
    }


def _spec_to_dict(spec) -> dict:
    return {
        "name": spec.name,
        "description": spec.description,
        "capability": spec.capability,
        "tags": list(spec.tags),
        "input_schema": spec.input_model.model_json_schema(),
        "output_schema": spec.output_model.model_json_schema(),
        "kind": "shared",
    }


@router.get("")
def list_agent_tools(tag: str | None = None):
    builtins = [_builtin_to_dict(t) for t in BUILTIN_TOOLS]

    specs = SharedToolRegistry.all()
    if tag:
        specs = [s for s in specs if tag in s.tags]
    shared = [_spec_to_dict(s) for s in specs]

    return {"items": builtins + shared}


@router.get("/{tool_name:path}")
def get_agent_tool(tool_name: str):
    spec = SharedToolRegistry.get(tool_name)
    if spec is None:
        raise HTTPException(404, f"Tool {tool_name!r} not found in registry")
    return _spec_to_dict(spec)
