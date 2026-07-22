"""APIContext — the single dependency bundle for FastAPI routes.

All route functions receive an ``APIContext`` via ``Depends(get_api_context)``
and access domain services through ``ctx.<service>``.  Store, DB, and Settings
are private to ``deps.py`` — only Service objects cross the boundary.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentbox.core.service import (
    AgentService,
    CredentialService,
    EngineService,
    EvaluationService,
    ExecutionService,
    ResourceService,
    SystemService,
    WorkspaceService,
)


@dataclass(frozen=True)
class APIContext:
    """The injected dependency bundle for FastAPI routes.

    Each field is a domain service.  Routes call ``ctx.<service>.<method>()``
    and never import ``core.service`` directly.
    """

    agents: AgentService
    workspaces: WorkspaceService
    resources: ResourceService
    execution: ExecutionService
    engines: EngineService
    evaluation: EvaluationService
    system: SystemService
    credentials: CredentialService
