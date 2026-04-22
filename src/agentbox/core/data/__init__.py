"""Persistent data + declarative models for agentbox.

Split into:
- ``schema``          — SQLAlchemy table definitions.
- ``records``         — DB return-shape dataclasses (RunRecord).
- ``store``           — SessionStore class (CRUD + composed mixins).
- ``analytics``       — Read-only aggregates (AnalyticsMixin).
- ``agent_versions``  — Agent version history (AgentVersionsMixin).
- ``transcripts``     — Filesystem JSONL transcript reader.
- ``manifest``        — Pydantic models for agentbox.toml + agent.toml.
"""

from agentbox.core.data.manifest import (
    AgentDef,
    AgentManifest,
    AgentSource,
    GuardrailRef,
    McpServerSpec,
    McpTransport,
    ProjectManifest,
    RunnerManifest,
    RunnerSpec,
    WorkspaceDef,
)
from agentbox.core.data.records import RunRecord
from agentbox.core.data.store import SessionStore
from agentbox.core.data.transcripts import read_transcript

__all__ = [
    "AgentDef",
    "AgentManifest",
    "AgentSource",
    "GuardrailRef",
    "McpServerSpec",
    "McpTransport",
    "ProjectManifest",
    "RunRecord",
    "RunnerManifest",
    "RunnerSpec",
    "SessionStore",
    "WorkspaceDef",
    "read_transcript",
]
