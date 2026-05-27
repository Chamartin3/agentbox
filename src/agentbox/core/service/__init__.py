"""Public service facade — the only import surface UI layers should use.

All api/, cli/, and mcp/ modules should import from here, never from
deep core internals. This keeps the internal organization private.
"""

# ── Data / persistence ────────────────────────────────────────────────
# ── Agent config / profiles / plugins ─────────────────────────────────
from agentbox.core.agent.config import build_config_json_payload
from agentbox.core.agent.plugins import backend_load_failure, backends, get_backend
from agentbox.core.agent.profiles import EffectiveRunnerConfig
from agentbox.core.agent.providers import get_provider, list_providers

# ── Constants ─────────────────────────────────────────────────────────
from agentbox.core.constants import EventType, ResourceType, RunStatus
from agentbox.core.data import read_transcript
from agentbox.core.data import AgentDef, AgentSource
from agentbox.core.data import VALID_POLICIES
from agentbox.core.data import RunnerProfile, RunnerProfileCreate
from agentbox.core.data import SessionStore

# ── Infra ─────────────────────────────────────────────────────────────
from agentbox.core.workspace.host_env import CAPABILITIES

# ── Prompt / composition ──────────────────────────────────────────────
from agentbox.core.agent.prompt.composition import compose_from_source
from agentbox.core.agent.prompt.composition import preview as composition_preview
from agentbox.core.agent.prompt.preview import (
    PreviewError,
    render_agent_prompt_preview,
)
from agentbox.core.agent.prompt.rendering import render_for_type
from agentbox.core.agent.prompt.resolver import resolve_prompt
from agentbox.core.resource.importers.host_path import HostPathImporter
from agentbox.core.resource.importers.schema import SchemaImporter
from agentbox.core.resource.importers.script import ScriptImporter
from agentbox.core.resource.importers.skill import SkillImporter
from agentbox.core.resource.importers.upload import UploadImporter
from agentbox.core.resource.importers.zip_upload import ZipUploadImporter

# ── Resources ─────────────────────────────────────────────────────────
from agentbox.core.resource.skills import discover_skills, find_skill
from agentbox.core.run.config import ConfigGenerator

# ── Run execution ─────────────────────────────────────────────────────
from agentbox.core.run.executor import NoBackendAvailable, RunExecutor
from agentbox.core.run.history import get as get_conversation
from agentbox.core.run.run_prep import (
    render_env_doc,
    resolve_agent_prompt_bindings,
    resolve_workspace_resources,
)

# ── Cross-cutting agents service ──────────────────────────────────────
from agentbox.core.service.agents import list_all_agents, resolve_agent
from agentbox.core.workspace.env_doc.renderers import AgentsMdRenderer, ClaudeMdRenderer
from agentbox.core.workspace.env_doc.schema import EnvDocContent

# ── Workspace ─────────────────────────────────────────────────────────
from agentbox.core.workspace.manager import (
    WorkspaceInfo,
    capabilities_path,
    claude_agents_path,
    claude_settings_path,
    ensure,
    info,
    list_all,
    load_capabilities,
    opencode_config_path,
    reset,
    resolve_path,
)
from agentbox.core.workspace.mcp.client import McpRegistry
from agentbox.core.workspace.sync import sync_workspace, sync_workspace_by_name
