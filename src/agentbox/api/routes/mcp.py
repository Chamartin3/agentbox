"""/mcp endpoints — tool manifest and server configuration."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from agentbox.api.deps import get_settings

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


@router.get("/manifest")
def get_mcp_manifest() -> dict:
    """Return the tool manifest with all available MCP tool groups."""
    settings = get_settings()
    manifest_path = settings.project_root / "bin" / "_generated" / "tool_manifest.json"
    if not manifest_path.is_file():
        raise HTTPException(404, "tool manifest not found")
    with open(manifest_path) as f:
        manifest = json.load(f)
    return {"manifest": manifest}


@router.get("/tool-groups")
def get_tool_groups() -> dict:
    """Return categorized tool groups for UI display."""
    settings = get_settings()
    manifest_path = settings.project_root / "bin" / "_generated" / "tool_manifest.json"
    if not manifest_path.is_file():
        raise HTTPException(404, "tool manifest not found")
    with open(manifest_path) as f:
        manifest = json.load(f)

    # Categorize by prefix
    categories: dict[str, list[dict]] = {}
    for group_name, tools in manifest.items():
        prefix = group_name.split(".")[0] if "." in group_name else "general"
        if prefix not in categories:
            categories[prefix] = []
        categories[prefix].append({
            "name": group_name,
            "tools": tools,
            "tool_count": len(tools),
        })

    return {
        "categories": categories,
        "total_groups": len(manifest),
        "total_tools": sum(len(tools) for tools in manifest.values()),
    }
