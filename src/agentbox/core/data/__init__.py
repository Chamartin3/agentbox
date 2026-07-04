"""Neutral data-shape leaf package.

Pure value types / TypedDicts / light helpers with no upward domain
dependencies. These were relocated from ``core.db`` to break the
cross-domain dependency on the persistence package.

``core.data`` may import only stdlib, third-party (pydantic, sqlalchemy
types), and ``core.constants``. It must NOT import ``core.db.*`` or any
domain package.
"""

from __future__ import annotations

from agentbox.core.data._util import hash_blobs, now_iso
from agentbox.core.data.claude_session import find_session_log, parse_session_log
from agentbox.core.data.manifests.agents import AgentDef, AgentManifest, AgentSource, CompositionConfig, SharedRef
from agentbox.core.data.manifests.engines import RunnerManifest, RunnerSpec
from agentbox.core.data.manifests.system import ProjectManifest
from agentbox.core.data.manifests.workspaces import McpServerSpec, McpTransport, WorkspaceDef, WorkspaceFile
from agentbox.core.data.profiles import (
    RunnerProfile,
    RunnerProfileCreate,
    RunnerProfilePatch,
    RunnerProfileStats,
)
from agentbox.core.data.records import RunRecord, SharedResourceRecord, row_to_run
from agentbox.core.data.rows import (
    AgentConfigEventRow,
    AgentMetaRow,
    AgentSyncRow,
    AgentToolGrantRow,
    AgentVersionCommentRow,
    AgentVersionFileRow,
    AgentVersionRatingRow,
    AgentVersionRow,
    ApiTokenPublicRow,
    ApiTokenRow,
    EnvDocRow,
    HostEnvCallLogRow,
    HostEnvProfileRow,
    PromptVersionRow,
    RepoResourceRow,
    ResourceStatus,
    RunCommentRow,
    UsageSummaryRow,
    VersionFileUploadRow,
    WorkspaceFileBindingRow,
    WorkspaceHostEnvGrantRow,
    WorkspaceMcpOverrideRow,
    WorkspaceMcpToolOverrideRow,
    WorkspaceRow,
    WorkspaceSource,
    _AgentConfigEventFields,
    _AgentMetaFields,
    _AgentMetaPatchFields,
    _AgentSyncFields,
    _AgentSyncPatchFields,
    _AgentToolGrantFields,
    _AgentToolGrantPatchFields,
    _AgentVersionCommentFields,
    _AgentVersionFields,
    _AgentVersionRatingFields,
    _PromptVersionFields,
)
from agentbox.core.data.snapshots import (
    HostEnvGrant,
    McpServerSnapshot,
    McpSnapshot,
    ResourceSnapshotEntry,
    RunnerSnapshot,
)
from agentbox.core.data.transcripts import read_transcript, resolve_transcript_path

__all__ = [
    "AgentConfigEventRow",
    "AgentDef",
    "AgentManifest",
    "AgentMetaRow",
    "AgentSource",
    "AgentSyncRow",
    "AgentToolGrantRow",
    "AgentVersionCommentRow",
    "AgentVersionFileRow",
    "AgentVersionRatingRow",
    "AgentVersionRow",
    "ApiTokenPublicRow",
    "ApiTokenRow",
    "CompositionConfig",
    "EnvDocRow",
    "HostEnvCallLogRow",
    "HostEnvGrant",
    "HostEnvProfileRow",
    "McpServerSnapshot",
    "McpServerSpec",
    "McpSnapshot",
    "McpTransport",
    "ProjectManifest",
    "PromptVersionRow",
    "RepoResourceRow",
    "ResourceSnapshotEntry",
    "ResourceStatus",
    "RunCommentRow",
    "RunnerManifest",
    "RunnerProfile",
    "RunnerProfileCreate",
    "RunnerProfilePatch",
    "RunnerProfileStats",
    "RunnerSnapshot",
    "RunnerSpec",
    "RunRecord",
    "SharedResourceRecord",
    "SharedRef",
    "UsageSummaryRow",
    "VersionFileUploadRow",
    "WorkspaceDef",
    "WorkspaceFile",
    "WorkspaceFileBindingRow",
    "WorkspaceHostEnvGrantRow",
    "WorkspaceMcpOverrideRow",
    "WorkspaceMcpToolOverrideRow",
    "WorkspaceRow",
    "WorkspaceSource",
    "find_session_log",
    "hash_blobs",
    "now_iso",
    "parse_session_log",
    "read_transcript",
    "resolve_transcript_path",
    "row_to_run",
    "_AgentConfigEventFields",
    "_AgentMetaFields",
    "_AgentMetaPatchFields",
    "_AgentSyncFields",
    "_AgentSyncPatchFields",
    "_AgentToolGrantFields",
    "_AgentToolGrantPatchFields",
    "_AgentVersionCommentFields",
    "_AgentVersionFields",
    "_AgentVersionRatingFields",
    "_PromptVersionFields",
]
