"""Shared fixtures for MCP resource/env-doc tool tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from agentbox.mcp.tools.resources import register
from fastmcp import FastMCP


@pytest.fixture
def mcp() -> FastMCP:
    """A FastMCP instance with the resource tools registered."""
    server = FastMCP("test")
    register(server)
    return server


@pytest.fixture
def ctx() -> MagicMock:
    """A mock request context with mock ``store`` and ``loader``."""
    obj = MagicMock()
    obj.store = MagicMock()
    obj.loader = MagicMock()
    return obj


@pytest.fixture
def get_tool_fn():
    """Return a helper resolving a registered tool's underlying function.

    Accesses FastMCP's ``_local_provider._components`` dict which stores
    ``FunctionTool`` objects keyed by ``"tool:<name>@"``.
    """

    def _get(mcp: FastMCP, name: str):
        return mcp._local_provider._components[f"tool:{name}@"].fn

    return _get
