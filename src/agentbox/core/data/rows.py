"""TypedDict row shapes returned by store queries.

These are the row-level contracts for query results, not SQLAlchemy models.
"""

from enum import StrEnum
from typing import Any, TypedDict


class EnvDocRow(TypedDict):
    id: str
    workspace_id: str
    version_number: int
    content_json: dict[str, Any]
    is_draft: int
    changelog: str
    created_at: str
    created_by: str | None


class PromptVersionRow(TypedDict):
    id: int
    agent_id: str
    version: int
    content: str
    author: str
    changelog: str
    content_hash: str | None
    created_at: str


class AgentVersionRow(TypedDict):
    """A row from ``agent_versions`` as returned by the agent-version reads.

    ``is_legacy`` is shaped to ``bool`` (the table stores 0/1).
    """

    id: int
    agent_id: str
    version: int
    source_path: str
    source_format: str
    content_snapshot: str
    prompt_snapshot: str
    content_hash: str
    author: str
    changelog: str
    is_legacy: bool
    created_at: str
    config_json: str | None
    prompt_content: str | None
    source: str
    resolved_tool_grants: list[str] | None


class RepoResourceRow(TypedDict):
    id: str
    slug: str
    type: str
    display_name: str
    description: str | None
    tags: str | None
    active_version_id: str | None
    status: str
    created_at: str
    updated_at: str
    created_by: str | None


class WorkspaceRow(TypedDict):
    name: str
    description: str | None
    path: str | None
    source: str
    created_at: str
    created_by: str | None
    updated_at: str


class AgentMetaRow(TypedDict):
    """A row from ``agent_meta`` as returned by agent-meta reads.

    ``export_to_disk`` is stored as 0/1 (int) — the table value, not a bool.
    """

    agent_id: str
    sync_mode: str
    export_to_disk: int
    source_path: str | None
    source_format: str | None
    created_at: str
    updated_at: str
    deleted_at: str | None
    disabled_at: str | None


class AgentToolGrantRow(TypedDict):
    """A row from ``agent_tool_grants``."""

    id: str
    agent_id: str
    tool_name: str
    changelog: str
    granted_at: str
    granted_by: str | None
    revoked_at: str | None
    revoked_by: str | None
    revoke_changelog: str | None


class AgentVersionCommentRow(TypedDict):
    """A row from ``agent_version_comments``."""

    id: int
    version_id: int
    author: str
    body: str
    created_at: str


class AgentVersionRatingRow(TypedDict):
    """A row from ``agent_version_ratings``."""

    version_id: int
    rating: int
    rater: str
    rated_at: str


class AgentVersionFileRow(TypedDict):
    """A row from ``agent_version_files``."""

    id: int
    version_id: int
    relative_path: str
    kind: str
    content: str
    sha256: str
    source_uri: str | None
    position: int
    created_at: str


class AgentSyncRow(TypedDict):
    """A row from ``agent_sync``."""

    agent_id: str
    proxy_path: str | None
    sync_mode: str
    sync_policy: str
    last_file_hash: str | None
    last_file_mtime: str | None
    last_sync_at: str | None


class AgentConfigEventRow(TypedDict):
    """A row from ``agent_config_events``."""

    id: int
    agent_id: str
    field: str
    from_value: str | None
    to_value: str | None
    author: str
    source: str
    created_at: str


class VersionFileUploadRow(TypedDict):
    """Result from :py:meth:`AgentService.upload_version_file`."""

    file: "AgentVersionFileRow"
    sha256: str
    size: int


# ── Execution / runs domain row shapes ────────────────────────────────


class SessionRow(TypedDict):
    """A row from ``sessions``."""

    id: str
    agent_id: str
    mode: str
    workdir: str | None
    created_at: str
    last_used_at: str | None


class UsageRow(TypedDict):
    """A row from ``usage``."""

    run_id: str
    model: str | None
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: float | None


class UsageSummaryRow(TypedDict):
    """Aggregate result from :py:meth:`UsageManager.aggregate_usage`."""

    input_tokens: int
    output_tokens: int
    cost_usd: float
    runs: int


class RunCommentRow(TypedDict):
    """A row from ``run_comments``."""

    id: int
    run_id: str
    author: str
    body: str
    created_at: str


class WebhookDeliveryRow(TypedDict):
    """A row from ``webhook_deliveries``."""

    id: int
    run_id: str
    attempt: int
    url: str
    payload_json: str | None
    response_status: int | None
    response_body: str | None
    latency_ms: int | None
    error: str | None
    ts: str


class RunVersionStats(TypedDict):
    """Per-agent-version aggregates over its runs (:py:meth:`RunManager.version_stats`)."""

    run_count: int
    avg_rating: float | None
    comment_count: int


class RichRunRow(TypedDict):
    """A row returned by :py:meth:`RunManager.list_runs_rich` (runs + usage join)."""

    id: str
    agent_id: str
    status: str
    created_at: str
    finished_at: str | None
    error: str | None
    session_id: str | None
    reported_model: str
    input_tokens: int | None
    output_tokens: int | None
    cache_read_tokens: int | None
    cache_creation_tokens: int | None
    cost_usd: float | None
    runner_profile_id: str | None
    runner_snapshot: str | None
    rating: int | None


class RunPagedRow(TypedDict):
    """A row returned by :py:meth:`RunManager.list_runs_paged` (all runs columns + usage + duration_ms)."""

    # runs table columns
    id: str
    agent_id: str
    session_id: str | None
    status: str
    input: str
    output: str | None
    error: str | None
    workdir: str | None
    transcript_path: str | None
    created_at: str
    finished_at: str | None
    config_digest: str | None
    agent_version_id: int | None
    composition_snapshot: str | None
    rendered_prompt: str | None
    variables: str | None
    validation_status: str | None
    validation_errors: str | None
    schema_validated_via: str | None
    post_status: str | None
    post_errors: str | None
    conversation_format: str | None
    conversation_uri: str | None
    runner_profile_id: str | None
    resource_snapshot: str | None
    mcp_snapshot: str | None
    runner_snapshot: str | None
    prompt_version_id: int | None
    rating: int | None
    # usage columns (NULL when no usage row for this run)
    input_tokens: int | None
    output_tokens: int | None
    cache_read_tokens: int | None
    cache_write_tokens: int | None
    cost_usd: float | None
    model: str | None
    # computed
    duration_ms: int | None


# ── Analytics aggregate shapes ─────────────────────────────────────────────


class ActivityTotalsRow(TypedDict):
    """Totals sub-dict in :class:`ActivitySummaryRow`."""

    runs: int
    running: int
    successes: int
    failures: int
    total_duration_ms: int
    avg_duration_ms: int
    failure_rate_pct: float
    input_tokens: int
    output_tokens: int
    cost_usd: float


class ActivitySeriesRow(TypedDict):
    """One day entry in the activity time-series."""

    date: str
    runs: int
    failures: int
    running: int
    ok: int
    error: int
    failed: int
    timeout: int
    incomplete: int


class ActivityByActionRow(TypedDict):
    """Per-agent breakdown entry in :class:`ActivitySummaryRow`."""

    action_name: str
    total: int
    failures: int
    avg_duration_ms: int
    total_input_tokens: int
    total_output_tokens: int


class ActivityByModelRow(TypedDict):
    """Per-model breakdown entry in :class:`ActivitySummaryRow`."""

    reported_model: str
    total: int
    failures: int
    total_input_tokens: int
    total_output_tokens: int


class ActivitySummaryRow(TypedDict):
    """Top-level return type of :py:meth:`RunManager.activity_summary`."""

    totals: ActivityTotalsRow
    series: list[ActivitySeriesRow]
    by_action: list[ActivityByActionRow]
    by_reported_model: list[ActivityByModelRow]


class RunStatsTotalsRow(TypedDict):
    """Totals sub-dict in :class:`RunStatsRow`."""

    runs: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    avg_duration_ms: int


class RunStatsByAgentRow(TypedDict):
    """Per-agent breakdown entry in :class:`RunStatsRow`."""

    agent_id: str
    runs: int
    tokens: int
    cost_usd: float


class RunStatsByModelRow(TypedDict):
    """Per-model breakdown entry in :class:`RunStatsRow`."""

    model: str
    runs: int
    tokens: int
    cost_usd: float


class RunStatsByVersionRow(TypedDict):
    """Per-version breakdown entry in :class:`RunStatsRow`."""

    version: int
    runs: int
    tokens: int


class RunStatsByStatusRow(TypedDict):
    """Per-status breakdown entry in :class:`RunStatsRow`."""

    status: str
    runs: int


class RunStatsTimeseriesRow(TypedDict):
    """Time-series bucket in :class:`RunStatsRow`."""

    bucket: str
    runs: int
    input_tokens: int
    output_tokens: int
    cost_usd: float


class RunStatsRow(TypedDict):
    """Top-level return type of :py:meth:`RunManager.stats_for_filters`."""

    totals: RunStatsTotalsRow
    by_agent: list[RunStatsByAgentRow]
    by_model: list[RunStatsByModelRow]
    by_version: list[RunStatsByVersionRow]
    by_status: list[RunStatsByStatusRow]
    timeseries: list[RunStatsTimeseriesRow]


# ── Workspace domain row shapes ────────────────────────────────────────────


class WorkspaceEnvDocPointerRow(TypedDict):
    """A row from ``workspace_env_docs`` (active-version pointer only)."""

    workspace_id: str
    active_version_id: str | None


class PermissionFileEntry(TypedDict, total=False):
    """One file-grant entry in workspace runtime permissions."""

    path: str
    mode: str
    size: int


class McpServerConfigView(TypedDict, total=False):
    """Effective MCP server config after manifest + override merge."""

    url: str | None
    transport: str
    command: list[str] | None
    cache_ttl: int


class WorkspaceMcpOverrideRow(TypedDict):
    """A row from ``workspace_mcp_overrides``."""

    id: str
    workspace_id: str
    server_name: str
    enabled: int
    config_overrides: McpServerConfigView | None
    changelog: str
    created_at: str
    created_by: str | None


class WorkspaceMcpToolOverrideRow(TypedDict):
    """A row from ``workspace_mcp_tool_overrides``."""

    id: str
    workspace_id: str
    server_name: str
    tool_name: str
    enabled: int
    created_at: str
    created_by: str | None




class AgentHostEnvGrantRow(TypedDict):
    """A row from ``agent_host_env_grants``."""

    agent_id: str
    profile_id: str | None
    overrides: dict[str, Any] | None
    changelog: str
    created_at: str
    created_by: str | None


class WorkspaceRuntimePermissionRow(TypedDict):
    """A row from ``workspace_runtime_permissions``."""

    workspace_id: str
    allowed_builtin_tools: list[str] | None
    files: list[PermissionFileEntry] | None
    max_tokens: int | None
    allow_file_write: int | None
    allow_network: int | None
    updated_at: str
    updated_by: str | None


class WorkspaceSubagentRow(TypedDict):
    """A row from ``workspace_subagents``."""

    id: str
    workspace_id: str
    agent_id: str
    alias: str
    display_order: int
    created_at: str
    created_by: str | None


# ── Resource domain row shapes ─────────────────────────────────────────────


class AgentPromptBindingRow(TypedDict):
    """A row from ``agent_prompt_resource_bindings``."""

    id: str
    agent_id: str
    resource_id: str
    marker: str | None
    mode: str | None
    slot: str | None
    attach_as_reference: int
    pinned_version_id: str | None
    display_order: int
    required: int
    changelog: str
    created_at: str
    created_by: str | None


class WorkspaceFileBindingRow(TypedDict):
    """A row from ``workspace_file_resource_bindings``."""

    id: str
    workspace_id: str
    resource_id: str
    target_path: str | None
    pinned_version_id: str | None
    materialize_mode: str
    on_conflict: str
    display_order: int
    changelog: str
    created_at: str
    created_by: str | None


class ResourceVersionRow(TypedDict):
    """A row from ``resource_versions``."""

    id: str
    resource_id: str
    version_number: int
    is_draft: int
    import_source: str
    source_metadata: str | None
    content_hash: str
    byte_size: int
    metadata_json: str | None
    changelog: str
    created_at: str
    created_by: str | None


class ResourceBlobRow(TypedDict):
    """A row from ``resource_blobs``."""

    id: str
    resource_version_id: str
    relative_path: str
    content: bytes
    content_text: str | None
    mime_type: str | None
    size_bytes: int


# ── System domain row shapes ───────────────────────────────────────────────


class ApiTokenRow(TypedDict):
    """A full row from ``api_tokens`` (includes encrypted secret)."""

    id: str
    environment: str
    name: str
    secret_encrypted: str
    last_four: str
    created_at: str
    updated_at: str


class ApiTokenPublicRow(TypedDict):
    """Public view returned by :py:meth:`ApiTokenManager.insert_token` (no secret)."""

    id: str
    environment: str
    name: str
    last_four: str
    created_at: str
    updated_at: str


class ApiTokenWithSecret(ApiTokenRow):
    """A token row plus the one-time plaintext ``secret`` (rotate/create result)."""

    secret: str


class HostEnvProfileRow(TypedDict):
    """A row from ``host_env_profiles``."""

    id: str
    name: str
    description: str | None
    grants: dict[str, Any]
    created_at: str
    created_by: str | None


class HostEnvCallLogRow(TypedDict):
    """A row from ``host_env_call_log``."""

    id: str
    run_id: str
    workspace_id: str
    capability: str
    params: dict[str, Any] | None
    status: str
    error: str | None
    surface: str
    created_at: str


class SettingKeyRow(TypedDict):
    """A ``{key, value_json}`` pair returned by :py:meth:`SettingManager.get_section`."""

    key: str
    value_json: str


# ── Manager insert / patch parameter shapes ──────────────────────────
# total=False — callers can pass any subset of columns (insert: all,
# patch: only the fields being updated).


class RunUpdateFields(TypedDict, total=False):
    """Partial-update fields for the runs table (all fields are optional).

    Used in RunManager methods to build UPDATE statements with selective columns.
    """

    status: str
    finished_at: str | None
    error: str | None
    output: str | None
    runner_profile_id: str | None
    agent_version_id: int | None
    validation_status: str | None
    validation_errors: str
    schema_validated_via: str | None
    conversation_format: str | None
    conversation_uri: str | None
    post_status: str
    post_errors: str
    rendered_prompt: str
    variables: str
    composition_snapshot: str
    resource_snapshot: str
    mcp_snapshot: str


class _AgentMetaFields(TypedDict, total=False):
    agent_id: str
    sync_mode: str
    export_to_disk: int
    source_path: str | None
    source_format: str | None
    created_at: str
    updated_at: str
    deleted_at: str | None
    disabled_at: str | None


class _AgentMetaPatchFields(TypedDict, total=False):
    """Fields patchable via AgentMetaManager.patch (agent_id is a WHERE param)."""

    sync_mode: str
    export_to_disk: int
    source_path: str | None
    source_format: str | None
    updated_at: str
    deleted_at: str | None
    disabled_at: str | None


class _AgentSyncFields(TypedDict, total=False):
    agent_id: str
    proxy_path: str | None
    sync_mode: str
    sync_policy: str
    last_file_hash: str | None
    last_file_mtime: str | None
    last_sync_at: str | None


class _AgentSyncPatchFields(TypedDict, total=False):
    """Fields patchable via AgentSyncManager.patch (agent_id is a WHERE param)."""

    proxy_path: str | None
    sync_mode: str
    sync_policy: str
    last_file_hash: str | None
    last_file_mtime: str | None
    last_sync_at: str | None


class _AgentConfigEventFields(TypedDict, total=False):
    agent_id: str
    field: str
    from_value: str | None
    to_value: str | None
    author: str
    source: str
    created_at: str


class _AgentVersionFields(TypedDict, total=False):
    agent_id: str
    version: int
    source_path: str
    source_format: str
    content_snapshot: str
    prompt_snapshot: str
    content_hash: str
    author: str
    changelog: str
    is_legacy: int
    created_at: str
    config_json: str | None
    prompt_content: str | None
    source: str
    resolved_tool_grants: list[str] | None


class _AgentVersionRatingFields(TypedDict, total=False):
    version_id: int
    rating: int
    rater: str
    rated_at: str


class _AgentVersionCommentFields(TypedDict, total=False):
    version_id: int
    author: str
    body: str
    created_at: str


class _PromptVersionFields(TypedDict, total=False):
    agent_id: str
    version: int
    content: str
    author: str
    changelog: str
    content_hash: str | None
    created_at: str


class _AgentToolGrantFields(TypedDict, total=False):
    id: str
    agent_id: str
    tool_name: str
    changelog: str
    granted_at: str
    granted_by: str | None
    revoked_at: str | None
    revoked_by: str | None
    revoke_changelog: str | None


class _AgentToolGrantPatchFields(TypedDict, total=False):
    """Fields patchable via AgentToolGrantManager.update_by_id (id is WHERE param)
    or revoke_active (agent_id, tool_name are WHERE params)."""

    changelog: str
    granted_at: str
    granted_by: str | None
    revoked_at: str | None
    revoked_by: str | None
    revoke_changelog: str | None


class ResourceStatus(StrEnum):
    ACTIVE = "active"
    DELETED = "deleted"


class WorkspaceSource(StrEnum):
    MANIFEST = "manifest"
    DB = "db"
