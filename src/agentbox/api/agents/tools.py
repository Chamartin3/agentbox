"""Read-only endpoints for the canonical tool catalog.

Returns the union of built-in canonical tools (``BUILTIN_TOOLS``) and
runtime-registered shared agent tools (``SharedToolRegistry``).
Authorization is handled by ``/api/agents/{id}/tool_grants``; this
endpoint is pure discovery.
"""

from __future__ import annotations

from typing import TypedDict

from fastapi import APIRouter, HTTPException

from agentbox.core.data import CanonicalTool
from agentbox.core.tools import BUILTIN_TOOLS, SharedToolRegistry
from agentbox.core.tools.builtin import BuiltinToolSpec
from agentbox.core.tools.registry import ToolSpec

router = APIRouter(prefix="/api/agent_tools", tags=["agent-tools-discovery"])


class _BuiltinToolDict(TypedDict):
    """Serialized builtin tool specification."""

    name: CanonicalTool
    description: str
    capability: CanonicalTool | None
    params: list[str]
    kind: str


class _SharedToolDict(TypedDict):
    """Serialized shared tool specification."""

    name: str
    description: str
    capability: str
    tags: list[str]
    input_schema: dict
    output_schema: dict
    kind: str


class _ToolListResult(TypedDict):
    """Response shape of GET /api/agent_tools."""

    items: list[_BuiltinToolDict | _SharedToolDict]


class _ToolDetailResult(_SharedToolDict):
    """Response shape of GET /api/agent_tools/{tool_name}."""

    pass


def _builtin_to_dict(spec: BuiltinToolSpec) -> _BuiltinToolDict:
    return {
        "name": spec.name,
        "description": spec.description,
        "capability": spec.capability,
        "params": list(spec.params),
        "kind": "builtin",
    }


def _spec_to_dict(spec: ToolSpec) -> _SharedToolDict:
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
def list_agent_tools(tag: str | None = None) -> _ToolListResult:
    builtins = [_builtin_to_dict(t) for t in BUILTIN_TOOLS]

    specs = SharedToolRegistry.all()
    if tag:
        specs = [s for s in specs if tag in s.tags]
    shared = [_spec_to_dict(s) for s in specs]

    return {"items": builtins + shared}


@router.get("/{tool_name:path}")
def get_agent_tool(tool_name: str) -> _ToolDetailResult:
    spec = SharedToolRegistry.get(tool_name)
    if spec is None:
        raise HTTPException(404, f"Tool {tool_name!r} not found in registry")
    return _spec_to_dict(spec)
