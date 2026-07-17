"""MCPContext — the injected dependency bundle for MCP tool functions.

All tools receive an ``MCPContext`` via the ``register(mcp, ctx)`` signature
and access domain services through ``ctx.<service>``.  Store, DB, and Settings
are private to ``deps.py`` — only Service objects cross the boundary.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentbox.core.service import (
    AgentService,
    EngineService,
    EvaluationService,
    ExecutionService,
    ResourceService,
    SystemService,
    WorkspaceService,
)
from agentbox.mcp.deps import _get_settings


@dataclass(frozen=True)
class MCPContext:
    """The injected dependency bundle for MCP tool closures.

    Each field is a domain service.  Tools call ``ctx.<service>.<method>()``
    and never import ``core.service`` directly.
    """

    agents: AgentService
    workspaces: WorkspaceService
    resources: ResourceService
    execution: ExecutionService
    engines: EngineService
    evaluation: EvaluationService
    system: SystemService


def get_mcp_context() -> MCPContext:
    """Cached singleton factory. Called once in ``build_server()``."""
    _get_settings()
    return MCPContext(
        agents=AgentService(),
        workspaces=WorkspaceService(),
        resources=ResourceService(),
        execution=ExecutionService(),
        engines=EngineService(),
        evaluation=EvaluationService(),
        system=SystemService(),
    )
