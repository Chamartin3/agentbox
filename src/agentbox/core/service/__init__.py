"""Public service facade — the only import surface UI layers should use.

All api/, cli/, and mcp/ modules should import from here, never from
deep core internals. This keeps the internal organization private.
"""

# ── Data / persistence ────────────────────────────────────────────────
# ── Agent config / profiles / plugins ─────────────────────────────────
from agentbox.core.engines import EffectiveRunnerConfig as EffectiveRunnerConfig
from agentbox.core.engines import get_provider as get_provider
from agentbox.core.engines import list_providers as list_providers

# ── Config ────────────────────────────────────────────────────────────
from agentbox.core.config import Settings as Settings

# ── Constants ─────────────────────────────────────────────────────────
from agentbox.core.data.constants import EventType as EventType
from agentbox.core.data.constants import ResourceType as ResourceType
from agentbox.core.data.constants import RunnerKind as RunnerKind
from agentbox.core.data.constants import RunStatus as RunStatus

# ── Errors ────────────────────────────────────────────────────────────
from agentbox.core.data.errors import AgentNotFound as AgentNotFound
from agentbox.core.data.errors import WorkspaceNotFound as WorkspaceNotFound
from agentbox.core.data import read_transcript as read_transcript
from agentbox.core.data import AgentDef as AgentDef
from agentbox.core.data import AgentSource as AgentSource
from agentbox.core.data import CompositionConfig as CompositionConfig
from agentbox.core.data import DoctorCheck as DoctorCheck
from agentbox.core.data import McpServerSpec as McpServerSpec
from agentbox.core.data import ProjectManifest as ProjectManifest
from agentbox.core.data import RunnerSpec as RunnerSpec
from agentbox.core.data import RunnerProfile as RunnerProfile
from agentbox.core.data import RunnerProfileCreate as RunnerProfileCreate
from agentbox.core.data import RunnerProfilePatch as RunnerProfilePatch
from agentbox.core.data import RunnerProfileStats as RunnerProfileStats
from agentbox.core.data import RunRecord as RunRecord
from agentbox.core.data import RunSummary as RunSummary
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
from agentbox.core.agents import PreviewError as PreviewError
from agentbox.core.agents import PromptError as PromptError
from agentbox.core.resources.importers.base import ImporterContext as ImporterContext
from agentbox.core.resources.importers.host_path import HostPathImporter as HostPathImporter
from agentbox.core.resources.importers.schema import SchemaImporter as SchemaImporter
from agentbox.core.resources.importers.script import ScriptImporter as ScriptImporter
from agentbox.core.resources.importers.skill import SkillImporter as SkillImporter
from agentbox.core.resources.importers.upload import UploadImporter as UploadImporter
from agentbox.core.resources.importers.zip import ZipUploadImporter as ZipUploadImporter

# ── Resources ─────────────────────────────────────────────────────────

# ── Run execution ─────────────────────────────────────────────────────
from agentbox.core.execution.orchestrate.setup import NoBackendAvailable as NoBackendAvailable
from agentbox.core.execution.orchestrate.executor import RunExecutor as RunExecutor

# ── Cross-cutting agents service ──────────────────────────────────────
from agentbox.core.service.agents import AgentService as AgentService

# ── Execution service ───────────────────────────────────────
from agentbox.core.service.execution import ExecutionService as ExecutionService

# ── Evaluation service (analytics) ──────────────────────────
from agentbox.core.service.evaluation import EvaluationService as EvaluationService
from agentbox.core.data.feedback import ActivityRange as ActivityRange

# ── Engines service ─────────────────────────────────────────
from agentbox.core.service.engines import EngineService as EngineService
from agentbox.core.service.engines import ProfileNotFound as ProfileNotFound

# ── System service ────────────────────────────────────────────────────
from agentbox.core.service.system import SystemService as SystemService

# ── Resources service ────────────────────────────────────────
from agentbox.core.service.resources import ResourceService as ResourceService
from agentbox.core.service.resources import InvalidResource as InvalidResource
from agentbox.core.service.resources import ResourceNotFound as ResourceNotFound

# ── Agent admin free functions (per-domain admin.py) ──

# ── Workspace ─────────────────────────────────────────────────────────
from agentbox.core.workspaces.workdir import WorkspaceInfo as WorkspaceInfo
from agentbox.core.workspaces.workdir import ensure as ensure
from agentbox.core.workspaces.workdir import info as info
from agentbox.core.workspaces.workdir import reset as reset
from agentbox.core.workspaces.workdir import resolve_path as resolve_path
from agentbox.core.workspaces.tooling.mcp import McpRegistry as McpRegistry

# ── WorkspaceService ────────────────────────────────────────
from agentbox.core.service.workspaces import WorkspaceService as WorkspaceService
from agentbox.core.service.workspaces import render_env_doc_preview as render_env_doc_preview

# ── DiagnosticsService ──────────────────────────────────────
from agentbox.core.service.diagnostics import DiagnosticsService as DiagnosticsService
