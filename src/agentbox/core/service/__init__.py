"""Public service facade — the only import surface UI layers should use.

All api/, cli/, and mcp/ modules should import from here, never from
deep core internals. This keeps the internal organization private.
"""

# ── Data / persistence ────────────────────────────────────────────────
# ── Agent config / profiles / plugins ─────────────────────────────────
from agentbox.core.agents.config import build_config_json_payload as build_config_json_payload
from agentbox.core.agents.composition.drift import _build_config_json as build_config_json_str  # noqa: F401
from agentbox.core.agents.resolve import engine_load_failure as backend_load_failure  # noqa: F401
from agentbox.core.agents.resolve import list_engines as backends  # noqa: F401
from agentbox.core.agents.resolve import resolve_engine_by_name as get_backend  # noqa: F401
from agentbox.core.engines import EffectiveRunnerConfig as EffectiveRunnerConfig
from agentbox.core.engines import get_provider as get_provider
from agentbox.core.engines import list_providers as list_providers

# ── Constants ─────────────────────────────────────────────────────────
from agentbox.core.constants import EventType as EventType
from agentbox.core.constants import ResourceType as ResourceType
from agentbox.core.constants import RunStatus as RunStatus
from agentbox.core.db import read_transcript as read_transcript
from agentbox.core.db import AgentDef as AgentDef
from agentbox.core.db import AgentSource as AgentSource
from agentbox.core.db import CompositionConfig as CompositionConfig
from agentbox.core.db import McpServerSpec as McpServerSpec
from agentbox.core.db import ProjectManifest as ProjectManifest
from agentbox.core.db import RunnerSpec as RunnerSpec
from agentbox.core.db import RunnerProfile as RunnerProfile
from agentbox.core.db import RunnerProfileCreate as RunnerProfileCreate
from agentbox.core.db import RunnerProfilePatch as RunnerProfilePatch
from agentbox.core.db import RunnerProfileStats as RunnerProfileStats
from agentbox.core.db import RunRecord as RunRecord
from agentbox.core.db import SessionStore as SessionStore
from agentbox.core.db import SharedResourceRecord as SharedResourceRecord
from agentbox.core.db import WorkspaceDef as WorkspaceDef

# ── Infra ─────────────────────────────────────────────────────────────
from agentbox.core.tools import CAPABILITIES as CAPABILITIES  # noqa: F401

# ── Prompt / composition ──────────────────────────────────────────────
from agentbox.core.agents.composition.bundle import compose_from_source as compose_from_source
from agentbox.core.agents.composition.bundle import preview as composition_preview  # noqa: F401
from agentbox.core.agents.composition.preview import PreviewError as PreviewError
from agentbox.core.agents.composition.preview import render_agent_prompt_preview as render_agent_prompt_preview
from agentbox.core.agents.composition.rendering import render_for_type as render_for_type
from agentbox.core.agents.composition.resolver import resolve_prompt as resolve_prompt
from agentbox.core.resources.importers.base import ImporterContext as ImporterContext
from agentbox.core.resources.importers.host_path import HostPathImporter as HostPathImporter
from agentbox.core.resources.importers.schema import SchemaImporter as SchemaImporter
from agentbox.core.resources.importers.script import ScriptImporter as ScriptImporter
from agentbox.core.resources.importers.skill import SkillImporter as SkillImporter
from agentbox.core.resources.importers.upload import UploadImporter as UploadImporter
from agentbox.core.resources.importers.zip import ZipUploadImporter as ZipUploadImporter

# ── Resources ─────────────────────────────────────────────────────────
from agentbox.core.resources.skills import discover_skills as discover_skills
from agentbox.core.resources.skills import find_skill as find_skill

# ── Run execution ─────────────────────────────────────────────────────
from agentbox.core.execution.orchestrate.setup import NoBackendAvailable as NoBackendAvailable
from agentbox.core.execution.orchestrate.executor import RunExecutor as RunExecutor
from agentbox.core.execution.observability.conversation import get as get_conversation  # noqa: F401
from agentbox.core.workspaces.prep import render_env_doc as render_env_doc
from agentbox.core.workspaces.prep import resolve_agent_prompt_bindings as resolve_agent_prompt_bindings
from agentbox.core.workspaces.prep import resolve_workspace_resources as resolve_workspace_resources

# ── Cross-cutting agents service ──────────────────────────────────────
from agentbox.core.service.agents.service import AgentService as AgentService
from agentbox.core.service.agents import build_agent_snapshot as build_agent_snapshot
from agentbox.core.service.agents import list_all_agents as list_all_agents
from agentbox.core.service.agents import resolve_agent as resolve_agent
from agentbox.core.service.agents.lifecycle import add_comment as add_version_comment  # noqa: F401
from agentbox.core.service.agents.lifecycle import branch_draft as branch_agent_draft  # noqa: F401
from agentbox.core.service.agents.lifecycle import create_agent as create_agent
from agentbox.core.service.agents.lifecycle import create_version as create_agent_version  # noqa: F401
from agentbox.core.service.agents.lifecycle import diff_versions as diff_agent_versions  # noqa: F401
from agentbox.core.service.agents.lifecycle import get_active_version as get_active_agent_version  # noqa: F401
from agentbox.core.service.agents.lifecycle import get_agent_def as get_agent_def
from agentbox.core.service.agents.lifecycle import get_prompt_version as get_prompt_version
from agentbox.core.service.agents.lifecycle import get_rating as get_version_rating  # noqa: F401
from agentbox.core.service.agents.lifecycle import get_version as get_agent_version  # noqa: F401
from agentbox.core.service.agents.lifecycle import grant_agent_tool as grant_agent_tool
from agentbox.core.service.agents.lifecycle import latest_version as latest_agent_version  # noqa: F401
from agentbox.core.service.agents.lifecycle import list_agent_tool_grants as list_agent_tool_grants
from agentbox.core.service.agents.lifecycle import list_comments as list_version_comments  # noqa: F401
from agentbox.core.service.agents.lifecycle import list_versions as list_agent_versions  # noqa: F401
from agentbox.core.service.agents.lifecycle import publish_version as publish_agent_version  # noqa: F401
from agentbox.core.service.agents.lifecycle import revoke_agent_tool as revoke_agent_tool
from agentbox.core.service.agents.lifecycle import rollback_to as rollback_agent_to  # noqa: F401
from agentbox.core.service.agents.lifecycle import save_prompt_revision as save_prompt_revision
from agentbox.core.service.agents.lifecycle import set_rating as set_version_rating  # noqa: F401
from agentbox.core.service.agents.lifecycle import soft_delete_agent as soft_delete_agent

# ── Execution service (plan 088) ───────────────────────────────────────
from agentbox.core.service.execution.service import ExecutionService as ExecutionService

# ── Evaluation service (plan 093 — analytics) ──────────────────────────
from agentbox.core.service.evaluation.service import EvaluationService as EvaluationService

# ── Engines service (plan 091 — deferred, circular import with providers) ──
# from agentbox.core.service.engines.service import EngineService as EngineService

# ── Repo resources service ─────────────────────────────────────────────
from agentbox.core.service.resources.repo import create_repo_resource as create_repo_resource
from agentbox.core.service.resources.repo import get_repo_resource_by_slug as get_repo_resource_by_slug
from agentbox.core.service.resources.repo import import_repo_version as import_repo_version
from agentbox.core.service.resources.repo import list_prompt_bindings as list_prompt_bindings
from agentbox.core.service.resources.repo import list_repo_resources as list_repo_resources
from agentbox.core.service.resources.repo import list_repo_versions as list_repo_versions
from agentbox.core.service.resources.repo import publish_repo_version as publish_repo_version
from agentbox.core.service.resources.repo import replace_prompt_bindings as replace_prompt_bindings
from agentbox.core.service.resources.repo import rollback_repo_resource as rollback_repo_resource

# ── System service ────────────────────────────────────────────────────
from agentbox.core.service.system.service import SystemService as SystemService

# ── Workspace admin service ────────────────────────────────────────────
from agentbox.core.service.execution.feedback import aggregate_usage as aggregate_usage
from agentbox.core.service.workspace_admin import get_active_env_doc as get_active_env_doc
from agentbox.core.service.workspace_admin import get_workspace as get_workspace
from agentbox.core.service.workspace_admin import get_workspace_host_env as get_workspace_host_env
from agentbox.core.service.workspace_admin import get_workspace_mcp_policy as get_workspace_mcp_policy
from agentbox.core.service.workspace_admin import list_env_doc_versions as list_env_doc_versions
from agentbox.core.service.workspace_admin import list_host_env_calls_for_run as list_host_env_calls_for_run
from agentbox.core.service.workspace_admin import list_host_env_profiles as list_host_env_profiles
from agentbox.core.service.workspace_admin import list_workspace_file_bindings as list_workspace_file_bindings
from agentbox.core.service.workspace_admin import list_workspace_mcp_server_overrides as list_workspace_mcp_server_overrides
from agentbox.core.service.workspace_admin import list_workspace_mcp_tool_overrides as list_workspace_mcp_tool_overrides
from agentbox.core.service.workspace_admin import publish_env_doc as publish_env_doc
from agentbox.core.service.workspace_admin import replace_version_config as replace_version_config
from agentbox.core.service.workspace_admin import replace_workspace_file_bindings as replace_workspace_file_bindings
from agentbox.core.service.workspace_admin import resolve_workspace_host_env as resolve_workspace_host_env
from agentbox.core.service.workspace_admin import rollback_env_doc as rollback_env_doc
from agentbox.core.service.workspace_admin import save_env_doc as save_env_doc
from agentbox.core.service.workspace_admin import set_workspace_mcp_policy as set_workspace_mcp_policy
from agentbox.core.service.workspace_admin import set_workspace_mcp_server_override as set_workspace_mcp_server_override
from agentbox.core.service.workspace_admin import update_agent_meta as update_agent_meta

# ── Workspace ─────────────────────────────────────────────────────────
from agentbox.core.workspaces.manager import WorkspaceInfo as WorkspaceInfo
from agentbox.core.workspaces.manager import claude_agents_path as claude_agents_path
from agentbox.core.workspaces.manager import claude_settings_path as claude_settings_path
from agentbox.core.workspaces.manager import ensure as ensure
from agentbox.core.workspaces.manager import info as info
from agentbox.core.service.workspaces.registry import (
    list_all_workspaces as list_all_workspaces,
)
from agentbox.core.service.workspaces import (
    get_workspace_mcp_tools as get_workspace_mcp_tools,
    launch_runner_configs as launch_runner_configs,
)
from agentbox.core.workspaces.manager import opencode_config_path as opencode_config_path
from agentbox.core.workspaces.manager import reset as reset
from agentbox.core.workspaces.manager import resolve_path as resolve_path
from agentbox.core.workspaces.mcp.client import McpRegistry as McpRegistry
from agentbox.core.workspaces.build import build_workspace as build_workspace
from agentbox.core.workspaces.build import build_workspace_by_name as build_workspace_by_name
