"""Public service facade — the only import surface UI layers should use.

All api/, cli/, and mcp/ modules should import from here, never from
deep core internals. This keeps the internal organization private.
"""

# ── Data / persistence ────────────────────────────────────────────────
# ── Agent config / profiles / plugins ─────────────────────────────────
from agentbox.core.agents import build_config_json_payload as build_config_json_payload
from agentbox.core.agents.versioning.drift import _build_config_json as build_config_json_str  # noqa: F401
from agentbox.core.agents import engine_load_failure as backend_load_failure  # noqa: F401
from agentbox.core.agents import list_engines as backends  # noqa: F401
from agentbox.core.agents import resolve_engine_by_name as get_backend  # noqa: F401
from agentbox.core.engines import EffectiveRunnerConfig as EffectiveRunnerConfig
from agentbox.core.engines import get_provider as get_provider
from agentbox.core.engines import list_providers as list_providers

# ── Constants ─────────────────────────────────────────────────────────
from agentbox.core.data.constants import EventType as EventType
from agentbox.core.data.constants import ResourceType as ResourceType
from agentbox.core.data.constants import RunStatus as RunStatus
from agentbox.core.data import read_transcript as read_transcript
from agentbox.core.data import AgentDef as AgentDef
from agentbox.core.data import AgentSource as AgentSource
from agentbox.core.data import CompositionConfig as CompositionConfig
from agentbox.core.data import McpServerSpec as McpServerSpec
from agentbox.core.data import ProjectManifest as ProjectManifest
from agentbox.core.data import RunnerSpec as RunnerSpec
from agentbox.core.data import RunnerProfile as RunnerProfile
from agentbox.core.data import RunnerProfileCreate as RunnerProfileCreate
from agentbox.core.data import RunnerProfilePatch as RunnerProfilePatch
from agentbox.core.data import RunnerProfileStats as RunnerProfileStats
from agentbox.core.data import RunRecord as RunRecord
from agentbox.core.data import WorkspaceDef as WorkspaceDef
from agentbox.core.data import AgentVersionRow as AgentVersionRow
from agentbox.core.data import AgentVersionCommentRow as AgentVersionCommentRow
from agentbox.core.data import AgentVersionRatingRow as AgentVersionRatingRow
from agentbox.core.data import ApiTokenPublicRow as ApiTokenPublicRow
from agentbox.core.data import ApiTokenRow as ApiTokenRow
from agentbox.core.data import EnvDocRow as EnvDocRow
from agentbox.core.data import HostEnvCallLogRow as HostEnvCallLogRow
from agentbox.core.data import HostEnvProfileRow as HostEnvProfileRow
from agentbox.core.data import RepoResourceRow as RepoResourceRow
from agentbox.core.data import RunCommentRow as RunCommentRow
from agentbox.core.data import SharedResourceRecord as SharedResourceRecord
from agentbox.core.data import UsageSummaryRow as UsageSummaryRow
from agentbox.core.data import WorkspaceFileBindingRow as WorkspaceFileBindingRow
from agentbox.core.data import AgentHostEnvGrantRow as AgentHostEnvGrantRow
from agentbox.core.data import WorkspaceMcpOverrideRow as WorkspaceMcpOverrideRow
from agentbox.core.data import WorkspaceMcpToolOverrideRow as WorkspaceMcpToolOverrideRow
from agentbox.core.engines.providers.base import ProviderDescriptor as ProviderDescriptor
from agentbox.core.engines.providers.base import ProviderModel as ProviderModel
from agentbox.core.engines.credentials.registry import CredentialMethod as CredentialMethod
from agentbox.core.engines.credentials.state import CredentialState as CredentialState
from agentbox.core.data.workenv import WorkspaceConfig as WorkspaceConfig
from agentbox.core.data.workenv import Recipe as Recipe

# ── Infra ─────────────────────────────────────────────────────────────
from agentbox.core.tools import CAPABILITIES as CAPABILITIES  # noqa: F401
from agentbox.core.tools import ToolSpec as ToolSpec

# ── Prompt / composition ──────────────────────────────────────────────
from agentbox.core.agents import compose_from_source as compose_from_source
from agentbox.core.agents import preview as composition_preview  # noqa: F401
from agentbox.core.agents import PreviewError as PreviewError
from agentbox.core.agents import render_agent_prompt_preview as render_agent_prompt_preview
from agentbox.core.agents import render_for_type as render_for_type
from agentbox.core.agents import resolve_prompt as resolve_prompt
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
from agentbox.core.agents import resolve_agent_prompt_bindings as resolve_agent_prompt_bindings

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

# ── Engines service (plan 091) ─────────────────────────────────────────
from agentbox.core.service.engines.service import EngineService as EngineService

# ── System service ────────────────────────────────────────────────────
from agentbox.core.service.system.service import SystemService as SystemService

# ── Resources service (plan 090) ────────────────────────────────────────
from agentbox.core.service.resources.service import ResourceService as ResourceService

# ── Workspace / resource / system admin free functions (per-domain admin.py) ──
from agentbox.core.service.agents.admin import replace_version_config as replace_version_config
from agentbox.core.service.agents.admin import update_agent_meta as update_agent_meta
from agentbox.core.service.resources.admin import list_workspace_file_bindings as list_workspace_file_bindings
from agentbox.core.service.resources.admin import replace_workspace_file_bindings as replace_workspace_file_bindings
from agentbox.core.service.system.admin import list_host_env_calls_for_run as list_host_env_calls_for_run
from agentbox.core.service.workspaces.admin import get_active_env_doc as get_active_env_doc
from agentbox.core.service.workspaces.admin import get_workspace as get_workspace
from agentbox.core.service.workspaces.admin import get_agent_host_env as get_agent_host_env
from agentbox.core.service.workspaces.admin import get_workspace_mcp_policy as get_workspace_mcp_policy
from agentbox.core.service.workspaces.admin import list_env_doc_versions as list_env_doc_versions
from agentbox.core.service.workspaces.admin import list_host_env_profiles as list_host_env_profiles
from agentbox.core.service.workspaces.admin import list_workspace_mcp_server_overrides as list_workspace_mcp_server_overrides
from agentbox.core.service.workspaces.admin import list_workspace_mcp_tool_overrides as list_workspace_mcp_tool_overrides
from agentbox.core.service.workspaces.admin import publish_env_doc as publish_env_doc
from agentbox.core.service.workspaces.admin import resolve_agent_host_env as resolve_agent_host_env
from agentbox.core.service.workspaces.admin import rollback_env_doc as rollback_env_doc
from agentbox.core.service.workspaces.admin import save_env_doc as save_env_doc
from agentbox.core.service.workspaces.admin import set_workspace_mcp_policy as set_workspace_mcp_policy
from agentbox.core.service.workspaces.admin import set_workspace_mcp_server_override as set_workspace_mcp_server_override

# ── Workspace ─────────────────────────────────────────────────────────
from agentbox.core.workspaces.workdir import WorkspaceInfo as WorkspaceInfo
from agentbox.core.workspaces.workdir import ensure as ensure
from agentbox.core.workspaces.workdir import info as info
from agentbox.core.service.workspaces.registry import (
    list_all_workspaces as list_all_workspaces,
)
from agentbox.core.service.workspaces import (
    get_workspace_mcp_tools as get_workspace_mcp_tools,
    launch_runner_configs as launch_runner_configs,
)
from agentbox.core.workspaces.workdir import reset as reset
from agentbox.core.workspaces.workdir import resolve_path as resolve_path
from agentbox.core.workspaces.tooling.mcp import McpRegistry as McpRegistry

# ── WorkspaceService (Plan 089) ────────────────────────────────────────
from agentbox.core.service.workspaces.service import WorkspaceService as WorkspaceService
from agentbox.core.service.workspaces.service import env_doc_body as env_doc_body
from agentbox.core.service.workspaces.service import render_env_doc_preview as render_env_doc_preview
from agentbox.core.service.workspaces.service import save_and_sync_env_doc as save_and_sync_env_doc
