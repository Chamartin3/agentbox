"""Agent and workspace definition loading.

The declarative models (``AgentDef``, ``RunnerSpec``, ``ProjectManifest``,
``WorkspaceDef``, ``GuardrailRef``) live in ``agentbox.core.data.manifest``
and are re-exported here for convenience.
"""

from agentbox.core.data.manifest import (
    AgentDef,
    GuardrailRef,
    ProjectManifest,
    RunnerSpec,
    WorkspaceDef,
)

from .agents_dir import scan_agents_dir
from .loader import DefinitionLoader
from .manifest_writer import ManifestWriter, PatchError
from .markdown import load_markdown_agent, write_markdown_agent

__all__ = [
    "AgentDef",
    "DefinitionLoader",
    "GuardrailRef",
    "ManifestWriter",
    "PatchError",
    "ProjectManifest",
    "RunnerSpec",
    "WorkspaceDef",
    "load_markdown_agent",
    "scan_agents_dir",
    "write_markdown_agent",
]
