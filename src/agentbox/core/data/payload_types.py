"""Shared TypedDict payload shapes — fixed-key dicts used across domains.

These are *not* Pydantic models: they are runtime dicts with known shapes
that cross module boundaries (dispatch payloads, resolver returns, etc.).
Each is a TypedDict so callers get structural type-checking without a
Pydantic dependency.

Every field carries its real static type — no ``Any``, no catch-all
JSON unions. JSON-schema documents use the structural ``JsonSchemaDict``.
"""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

from agentbox.core.data.rows import (
    AgentPromptBindingRow,
    AgentToolGrantRow,
    ApiTokenRow,
    EnvDocRow,
    HostEnvCallLogRow,
    HostEnvProfileRow,
    McpServerConfigView,
    PermissionFileEntry,
    RepoResourceRow,
    ResourceBlobRow,
    ResourceVersionRow,
    RunCommentRow,
    WorkspaceFileBindingRow,
    WorkspaceSubagentRow,
)


class UsagePayload(TypedDict):
    """Usage/cost data embedded in ``CompletionPayload`` and webhook bodies."""

    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    cache_read_tokens: NotRequired[int | None]
    cache_write_tokens: NotRequired[int | None]
    cost_usd: float | None
    duration_ms: NotRequired[int | None]


class RunCreatedResult(TypedDict):
    """``POST /api/runs`` response — the run was dispatched to a backend."""

    run_id: str
    agent: str


class RerunResult(RunCreatedResult):
    """``POST /api/runs/{run_id}/rerun`` — same shape as RunCreatedResult plus
    ``rerun_of`` pointing to the original run."""

    rerun_of: str


class RunLifecycleResult(TypedDict):
    """Terminal lifecycle action (complete / snapshot / post-outcome)."""

    ok: Literal[True]
    run_id: str
    status: NotRequired[str]
    post_status: NotRequired[str | None]


class CancelRunResult(TypedDict):
    """``POST /api/runs/{run_id}/cancel`` response."""

    run_id: str
    cancelled: bool
    status: str


class RunOutputResult(TypedDict):
    """MCP ``get_run_output`` — final output without surrounding metadata."""

    run_id: str
    output: str | None
    status: str


class RunErrorResult(TypedDict):
    """MCP ``get_run_errors`` — error details for a failed run."""

    run_id: str
    status: str
    error: str | None
    validation_status: str | None
    validation_errors: list[str] | None


class NotFoundResult(TypedDict):
    """Standard MCP tool error: requested resource was not found."""

    error: str
    run_id: str


class McpError(TypedDict):
    """Generic MCP-tool error envelope — the error arm of a tool's
    ``<Success> | McpError`` return. ``error`` is the code/message; the
    optional keys are context an individual tool attaches alongside it."""

    error: str
    agent_id: NotRequired[str]
    run_id: NotRequired[str]
    workspace_id: NotRequired[str]
    version: NotRequired[int]
    detail: NotRequired[str]


class EventStylesDict(TypedDict):
    """Mapping from every ``EventType`` (plus extras) to a Rich style string."""

    text: str
    log: str
    tool_call: str
    tool_result: str
    usage: str
    retry: str
    thinking: str
    timeout: str
    done: str
    error: str
    warning: str


class StubResult(TypedDict):
    """Ungranted-tool stub return — placeholder until the user grants access."""

    error: str
    tool: str


class EnvDocPreviewResult(TypedDict):
    """Preview of an env doc — same body rendered for every engine name."""

    claude_md: str
    agents_md: str


class RefSection(TypedDict):
    """Rendered reference section — one file's content with its heading."""

    heading: str
    content: str


class ChannelConfig(TypedDict, total=False):
    """Per-channel dispatch configuration.

    Superset of the keys read by the built-in channels (today: webhook).
    Channels validate the keys they need at runtime.
    """

    # ponytail: single flat config for the one existing channel; split into
    # per-channel TypedDicts + a generic base when a second channel lands.
    url: str
    headers: dict[str, str]
    retry_count: int
    retry_delay_seconds: float


WebhookChannelConfig = ChannelConfig
"""Deprecated alias — the webhook channel reads ``ChannelConfig`` directly."""


class RefreshProvidersResult(TypedDict):
    """Return shape of ``refresh_providers()``."""

    opencode: list[str]
    opencode_count: int
    model_cache_cleared: bool


type DiffValue = str | int | float | bool | None | dict[str, DiffValue] | list[DiffValue]
"""A fragment of user-authored config JSON inside a version diff.

Diffed snapshots are free-form ``config_json`` documents; the individual
changed values have no schema to type against.
"""


ChangedEntry = TypedDict("ChangedEntry", {"from": DiffValue, "to": DiffValue})


JsonDiffResult = TypedDict(
    "JsonDiffResult",
    {
        "added": dict[str, DiffValue],
        "removed": dict[str, DiffValue],
        "changed": dict[str, ChangedEntry],
        # Fallback keys when a snapshot is not valid JSON:
        "from": str,
        "to": str,
        "note": str,
    },
    total=False,
)
"""Key-level diff of two JSON snapshots (``_json_diff()``)."""


class AgentDiffResult(TypedDict):
    """Return shape of ``diff_versions()``."""

    from_version: int
    to_version: int
    prompt_diff: str
    content_diff: JsonDiffResult


class PromptVersionSummary(TypedDict):
    """One entry in ``PromptVersionListResult.versions``."""

    version: int
    is_draft: bool
    created_at: str
    author: str
    changelog: str
    size: int


class PromptVersionListResult(TypedDict):
    """Return shape of ``prompts.list_versions()``."""

    agent_id: str
    active_version: int | None
    draft_version: int | None
    versions: list[PromptVersionSummary]


class PromptVersionDetail(TypedDict):
    """Return shape of ``prompts.get_version()``."""

    version: int
    is_draft: bool
    created_at: str
    author: str
    changelog: str
    content: str
    size: int


JsonSchemaScalar = str | int | float | bool | None
"""A JSON-schema scalar leaf (``enum`` members, ``const`` values)."""


JsonSchemaDict = TypedDict(
    "JsonSchemaDict",
    {
        "type": "str | list[str]",
        "properties": "dict[str, JsonSchemaDict]",
        "required": "list[str]",
        "items": "JsonSchemaDict | list[JsonSchemaDict]",
        "oneOf": "list[JsonSchemaDict]",
        "anyOf": "list[JsonSchemaDict]",
        "allOf": "list[JsonSchemaDict]",
        "$defs": "dict[str, JsonSchemaDict]",
        "$ref": "str",
        "additionalProperties": "bool | JsonSchemaDict",
        "description": "str",
        "title": "str",
        "format": "str",
        "enum": "list[JsonSchemaScalar]",
        "const": "JsonSchemaScalar",
    },
    total=False,
)
"""Structural type for a JSON-Schema document — the keywords this
codebase actually reads (``assert_schema_consistent``, the token
backend's pydantic conversion, and prompt schema blocks)."""


class GrantConfig(TypedDict, total=False):
    """Per-capability host-env grant configuration.

    Union of every ``Capability.grant_schema`` in
    ``core/tools/capabilities.py`` — each capability reads its own subset.
    """

    allowed_paths: list[str]
    max_bytes: int
    command_allowlist: list[str]
    timeout_seconds: int
    cwd: str
    host_allowlist: list[str]
    methods: list[str]
    allowlist: list[str]


class ModelParams(TypedDict, total=False):
    """Provider model-settings passthrough (pydantic-ai ``model_settings``)."""

    temperature: float
    top_p: float
    max_tokens: int
    seed: int
    stop_sequences: list[str]
    presence_penalty: float
    frequency_penalty: float
    parallel_tool_calls: bool
    timeout: float
    extra_headers: dict[str, str]


class ExecutionSection(TypedDict):
    """``config_json["execution"]`` — see ``build_config_json_payload()``."""

    max_validation_retries: int
    max_error_retries: int
    output_validation_engine: str


class RuntimeSection(TypedDict):
    """``config_json["runtime"]``."""

    mcp_config_path: str | None
    allowed_tools: list[str]


class PythonSection(TypedDict):
    """``config_json["python"]``."""

    agent_module: str | None
    deps_factory: str | None
    output_schema_path: str | None


class ConfigJsonPayload(TypedDict):
    """The ``config_json`` top-level payload — fixed known sections."""

    execution: ExecutionSection
    runtime: RuntimeSection
    python: PythonSection


class AgentMetaDict(TypedDict, total=False):
    """Backend-specific agent metadata built by ``TokenBackend.render()``.

    All fields are optional (not every backend populates every field).
    """

    agent_module: str | None
    prompt: str
    agent_id: str
    model: str | None
    output_schema: JsonSchemaDict | None
    input_schema: JsonSchemaDict | None
    references: list[RefSection]
    timeout_seconds: int | None
    effective_tools: list[str]
    provider: str | None
    api_key_env: str | None
    base_url: str | None
    params: ModelParams | None
    profile_id: str | None
    output_mode: str | None
    output_retries: int
    host_env_grants: dict[str, GrantConfig] | None
    agent_tool_grants: list[str] | None
    host_env_workspace_id: str | None
    host_env_workdir: str | None
    host_env_db_path: str | None


class RenderMetadata(TypedDict):
    """Metadata attached to a rendered resource blob.

    ``role`` is always present; the counters only for multi-file renders.
    """

    role: str
    file_count: NotRequired[int]
    entry_path: NotRequired[str]
    missing_entry: NotRequired[bool]


class RenderedBlob(TypedDict):
    """Return shape of every ``render_*()`` function in composition/rendering."""

    text: str
    metadata: RenderMetadata


class ChannelSpec(TypedDict):
    """One dispatch channel entry — name + its configuration."""

    name: str
    config: ChannelConfig


class EnrichedRunRow(TypedDict):
    """One enriched run row as returned by ``list_runs_enriched()``."""

    id: str
    action_name: str
    backend: str
    configured_model: str | None
    reported_model: str | None
    state: str
    started_at: str | None
    completed_at: str | None
    duration_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    cache_read_tokens: int | None
    cache_creation_tokens: int | None
    cost_usd: float | None
    error: str | None
    session_id: str | None


class EnrichedRunsResult(TypedDict):
    """Return shape of ``list_runs_enriched()``."""

    results: list[EnrichedRunRow]
    total: int


class RunnerProfileRow(TypedDict):
    """A ``runner_profiles`` table row as returned by the manager."""

    id: str
    name: str
    description: str | None
    backend: str
    provider: str | None
    model: str | None
    base_url: str | None
    api_key_env: str | None
    api_token_id: str | None
    output_mode: str
    params: ModelParams
    headers: dict[str, str]
    extra_args: list[str]
    is_enabled: bool
    is_system_default: bool
    created_at: str
    updated_at: str


class RunnerProfileStatsRow(TypedDict):
    """Aggregated run statistics for a single runner profile."""

    profile_id: str
    runs: int
    succeeded: int
    failed: int
    input_tokens: int
    output_tokens: int
    cost_usd: float | None
    avg_duration_ms: float | None
    last_run_at: str | None


class CodexModelRow(TypedDict):
    """Compacted codex CLI model listing entry."""

    slug: str
    display_name: str
    description: str
    visibility: str
    supported_in_api: bool
    priority: int | None


class CredentialContext(TypedDict, total=False):
    """Context dict for ``Method.apply()``."""

    creds_base: str
    env_file: str


# ── Resource-service result shapes ─────────────────────────────────────────


class PromptBindingSpec(TypedDict):
    """Caller-supplied prompt-binding input (``replace_prompt_bindings``)."""

    resource_id: str
    id: NotRequired[str]
    binding_id: NotRequired[str]
    marker: NotRequired[str | None]
    mode: NotRequired[str | None]
    slot: NotRequired[str | None]
    attach_as_reference: NotRequired[bool | int]
    pinned_version_id: NotRequired[str | None]
    display_order: NotRequired[int]
    required: NotRequired[bool | int]


class WorkspaceBindingSpec(TypedDict):
    """Caller-supplied workspace file-binding input."""

    resource_id: str
    target_path: NotRequired[str | None]
    pinned_version_id: NotRequired[str | None]
    materialize_mode: NotRequired[str]
    on_conflict: NotRequired[str]
    display_order: NotRequired[int]


class ResourceDetailResult(TypedDict):
    """Return shape of ``ResourceService.get_resource()``."""

    resource: RepoResourceRow | None
    active_version: ResourceVersionRow | None


class ResourceVersionsResult(TypedDict):
    """Return shape of ``ResourceService.list_versions()``."""

    items: list[ResourceVersionRow]


class ResourceListResult(TypedDict):
    """Return shape of ``ResourceService.list_resources()``."""

    items: list[RepoResourceRow]
    total: int
    limit: int
    offset: int


class RenderedResourceResult(TypedDict):
    """Return shape of ``ResourceService.render_resource()``."""

    resource_id: str
    version_id: str
    text: str
    metadata: RenderMetadata


class ResourceTreeEntry(TypedDict):
    relative_path: str
    size_bytes: int | None
    mime_type: str | None


class ResourceTreeResult(TypedDict):
    """Return shape of ``ResourceService.get_tree()``."""

    version_id: str
    entries: list[ResourceTreeEntry]


class SchemaValidationErrorView(TypedDict):
    path: list[str | int]
    message: str


class ScriptSampleValidationResult(TypedDict):
    """Return shape of ``ResourceService.validate_script_sample()``."""

    valid: bool
    errors: list[SchemaValidationErrorView]
    schema_resource_id: str


class ResourcePreviewMode(TypedDict):
    mode: str
    text: str
    metadata: RenderMetadata


class ResourcePreviewModesResult(TypedDict):
    """Return shape of ``ResourceService.preview_modes()``."""

    modes: list[ResourcePreviewMode]


class EnrichedPromptBindingRow(TypedDict):
    """An ``AgentPromptBindingRow`` enriched with resource metadata.

    ``attach_as_reference`` is coerced to bool here (the raw row stores 0/1).
    """

    id: str
    agent_id: str
    resource_id: str
    marker: str | None
    mode: str | None
    slot: str | None
    attach_as_reference: bool
    pinned_version_id: str | None
    display_order: int
    required: int
    changelog: str
    created_at: str
    created_by: str | None
    resource_slug: str | None
    resource_type: str | None
    resource_display_name: str | None
    active_version_id: str | None


class PromptResourcesResult(TypedDict):
    """Return shape of ``ResourceService.list_prompt_resources()``."""

    items: list[EnrichedPromptBindingRow]


class PromptBindingItemsResult(TypedDict):
    """Return shape of ``ResourceService.replace_prompt_resources()``."""

    items: list[AgentPromptBindingRow]


class EnrichedWorkspaceBindingRow(WorkspaceFileBindingRow):
    """A ``WorkspaceFileBindingRow`` enriched with resource metadata."""

    resource_slug: str | None
    resource_type: str | None
    active_version_id: str | None


class WorkspaceResourcesResult(TypedDict):
    """Return shape of ``ResourceService.list_workspace_resources()``."""

    items: list[EnrichedWorkspaceBindingRow]


class WorkspaceBindingItemsResult(TypedDict):
    """Return shape of the workspace binding replace operations."""

    items: list[WorkspaceFileBindingRow]


class MaterializeDryRunEntry(TypedDict):
    binding_id: str
    resource_id: str
    resource_slug: str
    resource_type: str
    version_id: str
    target_path: str
    file_count: int
    materialize_mode: str
    on_conflict: str


class MaterializeConflict(TypedDict):
    binding_id: str
    issue: str


class MaterializeDryRunResult(TypedDict):
    """Return shape of ``ResourceService.dry_run_workspace_resources()``."""

    entries: list[MaterializeDryRunEntry]
    conflicts: list[MaterializeConflict]


class SkillCatalogItem(RepoResourceRow):
    """A skill resource row plus its workspace ``bound`` flag."""

    bound: bool


class SkillBindingsResult(TypedDict):
    """Return shape of ``ResourceService.list_workspace_skill_bindings()``."""

    items: list[SkillCatalogItem]


# ── Prompt-preview result shapes ────────────────────────────────────────────


class ResolvedPromptBinding(TypedDict):
    """A prompt binding resolved to its resource/version/blobs.

    Returned by ``resolve_agent_prompt_bindings`` for consumption by
    ``resolve_prompt`` and similar callers.
    """

    binding_id: str
    marker: str | None
    slot: str | None
    attach_as_reference: bool
    resource_id: str
    version_id: str
    content_hash: str
    type: str
    mode: str | None
    display_name: str
    required: bool
    blobs: list[ResourceBlobRow]


class ResolvedBindingView(TypedDict):
    """A prompt binding resolved to its resource/version/blobs for preview."""

    binding_id: str
    marker: str | None
    slot: str | None
    attach_as_reference: bool
    resource_id: str
    resource_slug: str
    version_id: str
    content_hash: str
    type: str
    mode: str | None
    display_name: str
    required: bool
    blobs: list[ResourceBlobRow]


class SchemaSlotView(TypedDict):
    """An input/output schema binding rendered for the preview payload."""

    binding_id: str
    resource_id: str
    version_id: str
    display_name: str | None
    content_hash: str
    text: str


class ReferenceMetaView(TypedDict):
    binding_id: str
    resource_id: str
    version_id: str
    display_name: str | None


class CharBreakdownPart(TypedDict):
    label: str
    chars: int
    kind: NotRequired[str]
    binding_id: NotRequired[str]
    resource_id: NotRequired[str]
    version_id: NotRequired[str]


class SnapshotEntryView(TypedDict):
    binding_id: str
    marker: str
    resource_id: str
    version_id: str
    content_hash: str
    mode: str
    chars: int


class HttpValidatorView(TypedDict):
    kind: Literal["http"]
    endpoint: str
    timeout_seconds: int
    description: str


class ScriptValidatorView(TypedDict):
    kind: Literal["script"]
    resource_id: str
    resource_slug: str | None
    resource_display_name: str | None
    pinned_version_id: str | None
    description: str


class ValidationView(TypedDict):
    """Structured validators payload shown under ``validation`` in previews."""

    validators: list[HttpValidatorView | ScriptValidatorView]


class AgentValidationResult(TypedDict):
    """Return shape of ``get_agent_validation()`` and ``put_agent_validation()``."""

    agent_id: str
    agent_version_id: int | None
    input: ValidationView | None
    output: ValidationView | None


class PromptPreviewResult(TypedDict):
    """Return shape of ``render_agent_prompt_preview()``."""

    rendered_prompt: str
    base_prompt: str
    template: str
    unresolved_markers: list[str]
    warnings: list[str]
    references: list[ReferenceMetaView]
    input_schema: SchemaSlotView | None
    output_schema: SchemaSlotView | None
    validation: ValidationView | None
    raw_text_output: bool
    char_breakdown: list[CharBreakdownPart]
    total_chars: int
    snapshot: list[SnapshotEntryView]


# ── Execution-service result shapes ─────────────────────────────────────────


class RunCommentsResult(TypedDict):
    """Return shape of ``list_comments()``."""

    run_id: str
    comments: list[RunCommentRow]


class RunFacetsResult(TypedDict):
    """Return shape of ``run_facets()``."""

    agents: list[str]
    executors: list[str]
    statuses: list[str]


class LogEntry(TypedDict):
    """One log-event row from ``ExecutionService.get_logs()``."""

    ts: str | None
    level: str
    message: str


class RunLogsResult(TypedDict):
    """Return shape of ``ExecutionService.get_logs()``."""

    items: list[LogEntry]
    total: int
    limit: int
    offset: int
    has_more: bool


# ── Workspace-service result shapes ─────────────────────────────────────────


class SubagentSpec(TypedDict):
    """Caller-supplied workspace subagent input."""

    agent_id: str
    alias: str
    display_order: NotRequired[int]


class WorkspaceListItem(TypedDict):
    """One entry from ``WorkspaceService.list_workspaces()``."""

    name: str
    path: str
    description: str | None
    source: str | None
    kind: str
    agents: list[str]
    agent_count: int
    file_count: int
    skill_count: int
    resource_count: int
    exists: bool
    on_disk: bool
    created_at: str | None
    updated_at: str | None


class WorkspaceDeleteResult(TypedDict):
    """Return shape of ``WorkspaceService.delete_workspace()``."""

    deleted: str
    counts: dict[str, int]
    disk_removed: bool


class EnvDocRenderEntry(TypedDict):
    """One snapshot entry produced by rendering the env doc into a workdir."""

    role: str
    file: str
    workspace_id: str
    env_doc_version_id: str
    bytes: int


class ResolvedMcpServer(TypedDict):
    name: str
    enabled: bool
    config: McpServerConfigView | None
    disabled_tools: list[str]
    source: str


class ResolvedWorkspaceMcp(TypedDict):
    """Return shape of ``WorkspaceService.resolve_workspace_mcp()``."""

    servers: list[ResolvedMcpServer]
    policy: str


class McpDiscoveryRefreshResult(TypedDict):
    invalidated: int


class ResolvedHostEnv(TypedDict):
    """Return shape of ``WorkspaceService.resolve_workspace_host_env()``."""

    grants: dict[str, GrantConfig]
    profile_id: str | None
    overrides: NotRequired[dict[str, GrantConfig] | None]


class WorkspaceFileRead(TypedDict):
    path: str
    content: str


class WorkspaceFileWrite(TypedDict):
    path: str
    bytes: int


class GeneratedConfigsResult(TypedDict):
    """Return shape of ``WorkspaceService.generate_configs()``."""

    workspace: str
    generated: dict[str, str]


class GeneratedSkillsResult(TypedDict):
    """Return shape of ``WorkspaceService.generate_skills()``."""

    workspace: str
    skills_count: int
    generated: dict[str, str]


class SkillListItem(TypedDict):
    name: str
    path: str
    size: int


class SkillsListResult(TypedDict):
    workspace: str
    workspace_path: str
    skills: list[SkillListItem]


class SkillContentResult(TypedDict):
    workspace: str
    skill: str
    path: str
    content: str


class EffectivePermissions(TypedDict):
    """Effective runtime permissions for one workspace."""

    allowed_tools: list[str]
    allowed_builtin_tools: list[str]
    files: list[PermissionFileEntry]
    max_tokens: int | None
    allow_file_write: bool
    allow_network: bool


class PermissionsPatch(TypedDict, total=False):
    """Caller-supplied permissions update (``set_permissions``)."""

    allowed_tools: list[str] | None
    allowed_builtin_tools: list[str] | None
    files: list[PermissionFileEntry] | None
    max_tokens: int | None
    allow_file_write: bool | None
    allow_network: bool | None


class PermissionsView(TypedDict):
    workspace: str
    path: str
    permissions: EffectivePermissions


class PermissionsSetResult(TypedDict):
    workspace: str
    path: str
    permissions: EffectivePermissions
    regenerated: dict[str, str]


class McpToolGroup(TypedDict):
    name: str
    tools: list[str]
    claude_tools: list[str]
    opencode_tools: list[str]
    tool_count: int
    kind: str
    active: NotRequired[bool]
    fully_active: NotRequired[bool]


class WorkspaceMcpToolsResult(TypedDict):
    """Return shape of ``WorkspaceService.get_workspace_mcp_tools()``."""

    workspace: str
    mcp_server_name: str
    claude_prefix: str
    opencode_prefix: str
    groups: list[McpToolGroup]
    builtin_tools: list[str]
    total_groups: int
    total_tools: int


class EnrichedSubagentRow(TypedDict):
    """A ``WorkspaceSubagentRow`` enriched with agent metadata (API layer)."""

    id: str
    workspace_id: str
    agent_id: str
    alias: str
    display_order: int
    created_at: str
    created_by: str | None
    agent_name: str | None
    agent_description: str | None


class SubagentItemsResult(TypedDict):
    items: list[EnrichedSubagentRow]


class SubagentRowsResult(TypedDict):
    items: list[WorkspaceSubagentRow]


class WorkspaceFileInfo(TypedDict):
    path: str
    size: int


class WorkspaceDetail(TypedDict):
    """Return shape of ``get_workspace_by_name()``."""

    name: str
    path: str
    exists: bool
    files: list[WorkspaceFileInfo]
    generated_configs: dict[str, str]


class AgentWorkspaceDetail(TypedDict):
    """Return shape of ``get_workspace_for_agent()``."""

    agent_id: str
    path: str
    exists: bool
    ephemeral: bool
    files: list[WorkspaceFileInfo]
    generated_configs: dict[str, str]


class WorkspacePathResult(TypedDict):
    path: str


class AgentSkillsResult(TypedDict):
    """Return shape of ``list_skills_for_agent()``."""

    agent_id: str
    workspace: str
    skills: list[SkillListItem]


class WorkspaceFileSnapshotEntry(TypedDict):
    """Snapshot row for one materialized workspace file binding."""

    role: str
    binding_id: str
    resource_id: str
    version_id: str
    content_hash: str
    target_path: str
    files_written: int
    mode: str
    skipped: bool
    skipped_reason: str | None


class PromptEmbedSnapshotEntry(TypedDict):
    """Snapshot row for one prompt-embedded resource binding."""

    role: str
    binding_id: str
    marker: str
    resource_id: str
    version_id: str
    content_hash: str
    mode: str


type RunSnapshotEntry = EnvDocRenderEntry | WorkspaceFileSnapshotEntry | PromptEmbedSnapshotEntry
"""Any JSON-serializable resource snapshot row captured during run prep."""


# ── 114: Area 2 (API routes) ───────────────────────────────────────────────


class EnrichedAgentListItem(TypedDict, total=False):
    """One enriched agent from list_agents_enriched()."""

    # Fields from AgentDef.model_dump()
    id: NotRequired[str]
    name: NotRequired[str]
    description: NotRequired[str | None]
    session_mode: NotRequired[str | None]
    workspace: NotRequired[str | None]
    tags: NotRequired[list[str]]
    tools: NotRequired[list[str]]
    webhook_url: NotRequired[str | None]
    headless: NotRequired[bool]
    runner: NotRequired[dict | None]
    composition: NotRequired[dict | None]
    # Enriched fields
    resolved_workspace: NotRequired[str]
    run_count: NotRequired[int]
    last_run_at: NotRequired[str | None]
    runner_profile_id: NotRequired[str | None]
    model: NotRequired[str | None]
    model_provider: NotRequired[str | None]
    updated_at: NotRequired[str | None]
    version: NotRequired[int | None]
    last_activity_at: NotRequired[str | None]
    disabled_at: NotRequired[str | None]


class AgentDetailWorkspace(TypedDict):
    """Workspace info nested in agent detail."""

    path: str
    ephemeral: bool
    generated_configs: dict[str, str]


class AgentVersionDetailItem(TypedDict):
    """One version in agent detail's versions list."""

    id: str
    version: int
    author: str | None
    changelog: str
    is_legacy: bool
    created_at: str
    has_comments: bool
    rating: int | None
    config_json: dict | None


class AgentDetailResult(TypedDict):
    """Return shape of get_agent_detail()."""

    agent: dict
    prompt: str
    composed_system: str | None
    composed_user: str | None
    runner_profile_id: str | None
    model: str | None
    model_provider: str | None
    workspace: AgentDetailWorkspace
    current_version: int | None
    versions: list[AgentVersionDetailItem]
    disabled_at: str | None


class SetWorkspaceResult(TypedDict):
    """Return shape of set_workspace() endpoint."""

    agent_id: str
    workspace: str | None


class PublishVersionResult(TypedDict):
    """Return shape of publish_version() endpoint."""

    active_version: int
    version_id: str | int | None
    version: int | None
    author: str | None
    changelog: str | None


class BranchDraftResult(TypedDict, total=False):
    """Return shape of branch_draft() endpoint."""

    version: int | str | None
    version_id: int | str | None
    author: str | None
    changelog: str | None


class DisableAgentResult(TypedDict):
    """Return shape of disable_agent() and enable_agent() endpoints."""

    agent_id: str
    disabled_at: str | None


class RollbackVersionResult(TypedDict, total=False):
    """Return shape of rollback_version() endpoint."""

    version: int | str | None
    version_id: int | str | None
    active_version: int | str | None
    author: str | None
    changelog: str | None


class BuiltinToolView(TypedDict):
    """Built-in tool entry in agent tools list."""

    name: str
    description: str
    capability: str | None
    params: list[str]
    kind: str


class SharedToolView(TypedDict):
    """Shared (registered) tool entry in agent tools list."""

    name: str
    description: str
    capability: str
    tags: list[str]
    input_schema: dict
    output_schema: dict
    kind: str


type AgentToolView = BuiltinToolView | SharedToolView
"""Union of builtin and shared tool views."""


class AgentToolsListResult(TypedDict):
    """Return shape of list_agent_tools() endpoint."""

    items: list[AgentToolView]


class ToolGrantResult(TypedDict, total=False):
    """Return shape of grant_tool() endpoint."""

    id: str
    agent_id: str | None
    tool_name: str
    granted_at: str | None
    granted_by: str | None
    revoked_at: str | None
    revoked_by: str | None
    changelog: str | None
    warning: str


class ToolGrantsResult(TypedDict):
    """Return shape of list_grants() endpoint."""

    items: list[AgentToolGrantRow]


class PatchAgentResult(TypedDict):
    """Return shape of patch_agent() endpoint."""

    agent: dict


class McpPolicyResult(TypedDict):
    """Return shape of get_policy() and set_policy() endpoints."""

    policy: str


class WorkspaceCatalogItem(TypedDict, total=False):
    """One item in available_tools() catalog."""

    name: str
    description: str
    kind: str
    server: str
    input_schema: dict | None
    grant_schema: dict | None
    resource_id: str
    target_path: str


class WorkspaceCatalogResult(TypedDict):
    """Return shape of list_available_tools() endpoint."""

    items: list[WorkspaceCatalogItem]


class HostCapabilityEntry(TypedDict):
    """One host capability in the capabilities list."""

    name: str
    description: str
    grant_schema: dict | None
    default_granted: bool


class HostCapabilitiesResult(TypedDict):
    """Return shape of list_capabilities() endpoint."""

    capabilities: list[HostCapabilityEntry]


class HostEnvProfilesResult(TypedDict):
    """Return shape of list_profiles() endpoint."""

    items: list[HostEnvProfileRow]


class HostEnvCallsResult(TypedDict):
    """Return shape of list_run_calls() endpoint."""

    items: list[HostEnvCallLogRow]


class SettingsSectionsResult(TypedDict):
    """Return shape of list_sections() endpoint."""

    known: list[str]
    present: list[str]


class SettingsSectionResult(TypedDict):
    """Return shape of get_section() endpoint."""

    section: str
    values: dict
    defaults: dict
    overrides: dict


class SettingsSectionPatchResult(TypedDict):
    """Return shape of patch_section() endpoint."""

    section: str
    values: dict


class ProjectMcpServersResult(TypedDict):
    """Return shape of list_project_mcp_servers() endpoint."""

    servers: list[dict]


class ProjectMcpServerDeleteResult(TypedDict):
    """Return shape of delete_project_mcp_server() endpoint."""

    deleted: str


class McpServersListResult(TypedDict):
    """Return shape of list_mcp_servers() endpoint."""

    servers: list
    overall_status: str


class McpServerToolEntry(TypedDict):
    """Tool entry in get_server_tools()."""

    name: str
    description: str
    input_schema: dict | None


class McpServerToolsResult(TypedDict):
    """Return shape of get_server_tools() endpoint."""

    server: str
    status: dict[str, str | int | bool | float | None | dict | list]
    tools: list[McpServerToolEntry]
    tool_count: int


class McpServerGroupEntry(TypedDict):
    """Group entry in get_server_groups()."""

    name: str
    tools: list[str]
    tool_count: int


class McpServerGroupsResult(TypedDict):
    """Return shape of get_server_groups() endpoint."""

    server: str
    groups: list[McpServerGroupEntry]
    group_count: int


class ApiTokensListResult(TypedDict):
    """Return shape of list_tokens() endpoint."""

    items: list[ApiTokenRow]
    total: int


class ApiTokenRotateResult(TypedDict, total=False):
    """Return shape of rotate_token() endpoint."""

    id: str
    environment: str | None
    name: str | None
    secret_suffix: str | None


class EnvDocResult(TypedDict):
    """Return shape of get_env_doc() endpoint."""

    active: EnvDocRow | None


class SubagentDetailItem(TypedDict):
    """One enriched subagent in list."""

    id: str
    workspace_id: str | None
    agent_id: str
    alias: str
    display_order: int
    created_at: str | None
    created_by: str | None
    agent_name: str | None
    agent_description: str | None


class SubagentListResult(TypedDict):
    """Return shape of list_workspace_subagents() endpoint."""

    items: list[SubagentDetailItem]


class SubagentReplaceResult(TypedDict):
    """Return shape of replace_workspace_subagents() endpoint."""

    items: list[WorkspaceSubagentRow]


class HealthReport(TypedDict, total=False):
    """Health status returned by health() endpoint."""

    ok: bool
    version: str
    mcp_servers: dict | None
    status: str | None
    mcp_error: NotRequired[str]


__all__ = [
    "AgentDetailResult",
    "AgentDetailWorkspace",
    "AgentToolsListResult",
    "AgentToolView",
    "AgentVersionDetailItem",
    "ApiTokenRotateResult",
    "ApiTokensListResult",
    "BranchDraftResult",
    "BuiltinToolView",
    "DisableAgentResult",
    "EnrichedAgentListItem",
    "EnvDocResult",
    "HealthReport",
    "HostCapabilitiesResult",
    "HostCapabilityEntry",
    "HostEnvCallsResult",
    "HostEnvProfilesResult",
    "McpPolicyResult",
    "McpServerGroupEntry",
    "McpServerGroupsResult",
    "McpServerToolEntry",
    "McpServerToolsResult",
    "McpServersListResult",
    "PatchAgentResult",
    "ProjectMcpServerDeleteResult",
    "ProjectMcpServersResult",
    "PublishVersionResult",
    "RollbackVersionResult",
    "SetWorkspaceResult",
    "SettingsSectionPatchResult",
    "SettingsSectionResult",
    "SettingsSectionsResult",
    "SharedToolView",
    "SubagentDetailItem",
    "SubagentListResult",
    "SubagentReplaceResult",
    "ToolGrantResult",
    "ToolGrantsResult",
    "WorkspaceCatalogItem",
    "WorkspaceCatalogResult",
    "WorkspacePathResult",
    "RunSnapshotEntry",
    "PromptEmbedSnapshotEntry",
    "WorkspaceFileSnapshotEntry",
    "AgentSkillsResult",
    "WorkspacePathResult",
    "AgentWorkspaceDetail",
    "WorkspaceDetail",
    "WorkspaceFileInfo",
    "EffectivePermissions",
    "EnrichedSubagentRow",
    "EnvDocRenderEntry",
    "GeneratedConfigsResult",
    "GeneratedSkillsResult",
    "McpDiscoveryRefreshResult",
    "McpServerConfigView",
    "McpServerConfigView",
    "McpToolGroup",
    "PermissionFileEntry",
    "PermissionsPatch",
    "PermissionsSetResult",
    "PermissionsView",
    "ResolvedHostEnv",
    "ResolvedMcpServer",
    "ResolvedWorkspaceMcp",
    "SkillContentResult",
    "SkillListItem",
    "SkillsListResult",
    "SubagentItemsResult",
    "SubagentRowsResult",
    "SubagentSpec",
    "WorkspaceDeleteResult",
    "WorkspaceFileRead",
    "WorkspaceFileWrite",
    "WorkspaceListItem",
    "WorkspaceMcpToolsResult",
    "AgentDiffResult",
    "ChangedEntry",
    "DiffValue",
    "JsonDiffResult",
    "AgentMetaDict",
    "ChannelConfig",
    "ChannelSpec",
    "CharBreakdownPart",
    "CodexModelRow",
    "ConfigJsonPayload",
    "CredentialContext",
    "EnrichedPromptBindingRow",
    "EnrichedRunRow",
    "EnrichedRunsResult",
    "EnrichedWorkspaceBindingRow",
    "ExecutionSection",
    "GrantConfig",
    "HttpValidatorView",
    "JsonSchemaDict",
    "JsonSchemaScalar",
    "ModelParams",
    "MaterializeConflict",
    "MaterializeDryRunEntry",
    "MaterializeDryRunResult",
    "PromptBindingItemsResult",
    "PromptBindingSpec",
    "PromptPreviewResult",
    "PromptResourcesResult",
    "PythonSection",
    "RuntimeSection",
    "ReferenceMetaView",
    "RefreshProvidersResult",
    "RenderMetadata",
    "RenderedBlob",
    "RenderedResourceResult",
    "ResolvedBindingView",
    "ResourceDetailResult",
    "ResourcePreviewMode",
    "ResourcePreviewModesResult",
    "ResourceTreeEntry",
    "ResourceTreeResult",
    "ResourceVersionsResult",
    "RunnerProfileRow",
    "RunnerProfileStatsRow",
    "SchemaSlotView",
    "SchemaValidationErrorView",
    "ScriptSampleValidationResult",
    "ScriptValidatorView",
    "SkillBindingsResult",
    "SkillCatalogItem",
    "SnapshotEntryView",
    "UsagePayload",
    "AgentValidationResult",
    "LogEntry",
    "PromptVersionDetail",
    "PromptVersionListResult",
    "PromptVersionSummary",
    "ResourceListResult",
    "RunCommentsResult",
    "RunFacetsResult",
    "RunLogsResult",
    "ValidationView",
    "WebhookChannelConfig",
    "WorkspaceBindingItemsResult",
    "WorkspaceBindingSpec",
    "WorkspaceResourcesResult",
]
