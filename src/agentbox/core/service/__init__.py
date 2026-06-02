"""Public service facade — the only import surface UI layers should use.

All api/, cli/, and mcp/ modules should import from here, never from
deep core internals. This keeps the internal organization private.
"""

# ── Data / persistence ────────────────────────────────────────────────
# ── Agent config / profiles / plugins ─────────────────────────────────
from agentbox.core.agent.config import build_config_json_payload as build_config_json_payload
from agentbox.core.agent.resolve import engine_load_failure as backend_load_failure  # noqa: F401
from agentbox.core.agent.resolve import list_engines as backends  # noqa: F401
from agentbox.core.agent.resolve import resolve_engine_by_name as get_backend  # noqa: F401
from agentbox.core.agent.profiles import EffectiveRunnerConfig as EffectiveRunnerConfig
from agentbox.core.agent.providers import get_provider as get_provider
from agentbox.core.agent.providers import list_providers as list_providers

# ── Constants ─────────────────────────────────────────────────────────
from agentbox.core.constants import EventType as EventType
from agentbox.core.constants import ResourceType as ResourceType
from agentbox.core.constants import RunStatus as RunStatus
from agentbox.core.data import read_transcript as read_transcript
from agentbox.core.data import AgentDef as AgentDef
from agentbox.core.data import AgentSource as AgentSource
from agentbox.core.data import CompositionConfig as CompositionConfig
from agentbox.core.data import RunnerSpec as RunnerSpec
from agentbox.core.data import VALID_POLICIES as VALID_POLICIES
from agentbox.core.data import RunnerProfile as RunnerProfile
from agentbox.core.data import RunnerProfileCreate as RunnerProfileCreate
from agentbox.core.data import SessionStore as SessionStore
from agentbox.core.data import WorkspaceDef as WorkspaceDef

# ── Infra ─────────────────────────────────────────────────────────────
from agentbox.core.tools import CAPABILITIES as CAPABILITIES  # noqa: F401

# ── Prompt / composition ──────────────────────────────────────────────
from agentbox.core.agent.prompt.composition import compose_from_source as compose_from_source
from agentbox.core.agent.prompt.composition import preview as composition_preview  # noqa: F401
from agentbox.core.agent.prompt.preview import PreviewError as PreviewError
from agentbox.core.agent.prompt.preview import render_agent_prompt_preview as render_agent_prompt_preview
from agentbox.core.agent.prompt.rendering import render_for_type as render_for_type
from agentbox.core.agent.prompt.resolver import resolve_prompt as resolve_prompt
from agentbox.core.resource.importers.host_path import HostPathImporter as HostPathImporter
from agentbox.core.resource.importers.schema import SchemaImporter as SchemaImporter
from agentbox.core.resource.importers.script import ScriptImporter as ScriptImporter
from agentbox.core.resource.importers.skill import SkillImporter as SkillImporter
from agentbox.core.resource.importers.upload import UploadImporter as UploadImporter
from agentbox.core.resource.importers.zip_upload import ZipUploadImporter as ZipUploadImporter

# ── Resources ─────────────────────────────────────────────────────────
from agentbox.core.resource.skills import discover_skills as discover_skills
from agentbox.core.resource.skills import find_skill as find_skill
from agentbox.core.run.config import ConfigGenerator as ConfigGenerator

# ── Run execution ─────────────────────────────────────────────────────
from agentbox.core.run.executor import NoBackendAvailable as NoBackendAvailable
from agentbox.core.run.executor import RunExecutor as RunExecutor
from agentbox.core.run.history import get as get_conversation  # noqa: F401
from agentbox.core.run.run_prep import render_env_doc as render_env_doc
from agentbox.core.run.run_prep import resolve_agent_prompt_bindings as resolve_agent_prompt_bindings
from agentbox.core.run.run_prep import resolve_workspace_resources as resolve_workspace_resources

# ── Cross-cutting agents service ──────────────────────────────────────
from agentbox.core.service.agents import list_all_agents as list_all_agents
from agentbox.core.service.agents import resolve_agent as resolve_agent
from agentbox.core.service.agent_lifecycle import add_comment as add_version_comment  # noqa: F401
from agentbox.core.service.agent_lifecycle import branch_draft as branch_agent_draft  # noqa: F401
from agentbox.core.service.agent_lifecycle import clear_agent_runner_profile as clear_agent_runner_profile
from agentbox.core.service.agent_lifecycle import create_agent as create_agent
from agentbox.core.service.agent_lifecycle import create_version as create_agent_version  # noqa: F401
from agentbox.core.service.agent_lifecycle import diff_versions as diff_agent_versions  # noqa: F401
from agentbox.core.service.agent_lifecycle import get_active_version as get_active_agent_version  # noqa: F401
from agentbox.core.service.agent_lifecycle import get_agent_def as get_agent_def
from agentbox.core.service.agent_lifecycle import get_agent_runner_profile as get_agent_runner_profile
from agentbox.core.service.agent_lifecycle import get_prompt_version as get_prompt_version
from agentbox.core.service.agent_lifecycle import get_rating as get_version_rating  # noqa: F401
from agentbox.core.service.agent_lifecycle import get_version as get_agent_version  # noqa: F401
from agentbox.core.service.agent_lifecycle import grant_agent_tool as grant_agent_tool
from agentbox.core.service.agent_lifecycle import latest_version as latest_agent_version  # noqa: F401
from agentbox.core.service.agent_lifecycle import list_agent_tool_grants as list_agent_tool_grants
from agentbox.core.service.agent_lifecycle import list_comments as list_version_comments  # noqa: F401
from agentbox.core.service.agent_lifecycle import list_versions as list_agent_versions  # noqa: F401
from agentbox.core.service.agent_lifecycle import publish_version as publish_agent_version  # noqa: F401
from agentbox.core.service.agent_lifecycle import revoke_agent_tool as revoke_agent_tool
from agentbox.core.service.agent_lifecycle import rollback_to as rollback_agent_to  # noqa: F401
from agentbox.core.service.agent_lifecycle import save_prompt_revision as save_prompt_revision
from agentbox.core.service.agent_lifecycle import set_agent_runner_profile as set_agent_runner_profile  # noqa: F401
from agentbox.core.service.agent_lifecycle import set_rating as set_version_rating  # noqa: F401
from agentbox.core.service.agent_lifecycle import soft_delete_agent as soft_delete_agent

# ── Runner profiles service ────────────────────────────────────────────
from agentbox.core.service.runner_profiles import create_runner_profile as create_runner_profile
from agentbox.core.service.runner_profiles import delete_runner_profile as delete_runner_profile
from agentbox.core.service.runner_profiles import get_runner_profile as get_runner_profile
from agentbox.core.service.runner_profiles import list_runner_profile_stats as list_runner_profile_stats
from agentbox.core.service.runner_profiles import list_runner_profiles as list_runner_profiles
from agentbox.core.service.runner_profiles import runner_profile_stats as runner_profile_stats
from agentbox.core.service.runner_profiles import set_agent_runner_profile as bind_runner_profile  # noqa: F401

# ── Repo resources service ─────────────────────────────────────────────
from agentbox.core.service.repo_resources import create_repo_resource as create_repo_resource
from agentbox.core.service.repo_resources import get_repo_resource_by_slug as get_repo_resource_by_slug
from agentbox.core.service.repo_resources import import_repo_version as import_repo_version
from agentbox.core.service.repo_resources import list_prompt_bindings as list_prompt_bindings
from agentbox.core.service.repo_resources import list_repo_resources as list_repo_resources
from agentbox.core.service.repo_resources import list_repo_versions as list_repo_versions
from agentbox.core.service.repo_resources import publish_repo_version as publish_repo_version
from agentbox.core.service.repo_resources import replace_prompt_bindings as replace_prompt_bindings
from agentbox.core.service.repo_resources import rollback_repo_resource as rollback_repo_resource

# ── System admin service ───────────────────────────────────────────────
from agentbox.core.service.system_admin import create_api_token as create_api_token
from agentbox.core.service.system_admin import delete_api_token as delete_api_token
from agentbox.core.service.system_admin import delete_project_mcp_server as delete_project_mcp_server
from agentbox.core.service.system_admin import get_project_mcp_servers as get_project_mcp_servers
from agentbox.core.service.system_admin import get_settings_section as get_settings_section
from agentbox.core.service.system_admin import list_api_tokens as list_api_tokens
from agentbox.core.service.system_admin import list_settings_sections as list_settings_sections
from agentbox.core.service.system_admin import rotate_api_token as rotate_api_token
from agentbox.core.service.system_admin import set_project_mcp_server as set_project_mcp_server
from agentbox.core.service.system_admin import set_project_shared_asset as set_project_shared_asset
from agentbox.core.service.system_admin import set_setting as set_setting
from agentbox.core.service.system_admin import update_settings_section as update_settings_section

# ── Workspace admin service ────────────────────────────────────────────
from agentbox.core.service.workspace_admin import aggregate_usage as aggregate_usage
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
from agentbox.core.workspace.env_doc.renderers import AgentsMdRenderer as AgentsMdRenderer
from agentbox.core.workspace.env_doc.renderers import ClaudeMdRenderer as ClaudeMdRenderer
from agentbox.core.workspace.env_doc.schema import EnvDocContent as EnvDocContent

# ── Workspace ─────────────────────────────────────────────────────────
from agentbox.core.workspace.manager import WorkspaceInfo as WorkspaceInfo
from agentbox.core.workspace.manager import capabilities_path as capabilities_path
from agentbox.core.workspace.manager import claude_agents_path as claude_agents_path
from agentbox.core.workspace.manager import claude_settings_path as claude_settings_path
from agentbox.core.workspace.manager import ensure as ensure
from agentbox.core.workspace.manager import info as info
from agentbox.core.workspace.manager import list_all as list_all
from agentbox.core.workspace.manager import load_capabilities as load_capabilities
from agentbox.core.workspace.manager import opencode_config_path as opencode_config_path
from agentbox.core.workspace.manager import reset as reset
from agentbox.core.workspace.manager import resolve_path as resolve_path
from agentbox.core.workspace.mcp.client import McpRegistry as McpRegistry
from agentbox.core.workspace.build import build_workspace as build_workspace
from agentbox.core.workspace.build import build_workspace_by_name as build_workspace_by_name
