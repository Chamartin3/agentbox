"""MCP tools for resource bindings, env-docs, MCP policy, and host-env grants."""

from __future__ import annotations

from fastmcp import FastMCP

from agentbox.mcp.tools.resources.bindings import _require_reason, register_bindings
from agentbox.mcp.tools.resources.importers import register_importers
from agentbox.mcp.tools.resources.prompts import register_prompts
from agentbox.mcp.tools.resources.repo import register_repo
from agentbox.mcp.tools.resources.workspace import register_workspace

__all__ = ["_require_reason", "register"]


def register(mcp: FastMCP) -> None:
    register_repo(mcp)
    register_importers(mcp)
    register_bindings(mcp)
    register_prompts(mcp)
    register_workspace(mcp)
