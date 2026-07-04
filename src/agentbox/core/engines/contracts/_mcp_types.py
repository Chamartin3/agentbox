"""MCP tool type definitions shared across backends."""

from __future__ import annotations

from typing import Any, TypedDict



class McpToolSpec(TypedDict, total=False):
    name: str
    description: str
    inputSchema: dict[str, Any]
