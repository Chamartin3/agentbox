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

from agentbox.core.data.jsontypes import RawJson, RawJsonValue
from agentbox.core.data.workenv import SourceMetadata
from agentbox.core.data.rows import (
    AgentPromptBindingRow,
    McpServerConfigView,
    PermissionFileEntry,
    RepoResourceRow,
    ResourceBlobRow,
    ResourceVersionRow,
    RunCommentRow,
    RunPagedRow,
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


# ── Run-related payload shapes ─────────────────────────────────────────────────


class PromptFragmentPayload(TypedDict):
    """A single prompt fragment in a run's assembled prompt."""

    name: str
    """Short label, e.g. 'user_input', 'agent_system_prompt'."""

    source: str
    """'user', 'agent_def', 'project', 'agentbox', 'claude_cli'."""

    injected_by: str
    """Which layer pushes this text into the model: 'agentbox', 'claude_cli', 'token'."""

    content: str
    """The actual text. May be a note for things we cannot inspect."""

    inspectable: bool
    """False = we describe what's there but don't have the bytes."""

    shared_resource_id: NotRequired[str | None]
    """Optional: id of the shared resource this fragment came from."""

    shared_resource_version: NotRequired[int | None]
    """Optional: version of the shared resource (None = active version was used)."""

    size_bytes: int
    """Size of the content in bytes."""


class RunnerSnapshot(TypedDict):
    """Append-only snapshot of the runner config that executed a run."""

    profile_id: str | None
    profile_name: str | None
    backend: str | None
    model: str | None
    timeout_seconds: int | None
    provider: str | None
    extra_args: list[str]
    source: str | None
    overrides_applied: RawJson
    captured_at: str


class RunnerSnapshotInvalid(TypedDict):
    """Placeholder when a run's stored runner snapshot failed to parse."""

    snapshot: Literal["invalid"]
    raw: str


class RunnerSnapshotMissing(TypedDict):
    """Placeholder when a run has no stored runner snapshot."""

    snapshot: Literal["missing"]


# The read-side view of a run's runner snapshot: a valid parse, or one of the
# two placeholders when the stored JSON was absent/unparseable.
type RunnerSnapshotView = RunnerSnapshot | RunnerSnapshotInvalid | RunnerSnapshotMissing


class RunDetailPayload(TypedDict):
    """A single run with all its details (Run table + enrichment + snapshots)."""

    # Runs table columns (non-optional as they're created with defaults)
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
    runner_snapshot: RunnerSnapshotView | None
    # Enriched fields added by get_run_detail
    agent_version: int | None
    backend: str | None
    configured_model: str | None
    reported_model: str | None
    prompt_version_id: int | None


class PaginatedRunItem(RunPagedRow, total=False):
    """A run item in paginated results (RunPagedRow + agent_version enrichment)."""

    agent_version: int | None


class RunDetailResult(TypedDict):
    """Return shape of ``GET /api/runs/{run_id}`` and ``ExecutionService.get_run_detail``."""

    run: RunDetailPayload
    usage: UsagePayload | None


class RunPromptFragmentsResult(TypedDict):
    """Return shape of ``GET /api/runs/{run_id}/prompt``."""

    run_id: str
    fragments: list[PromptFragmentPayload]
    total_bytes: int


class PaginatedRunsResult(TypedDict):
    """Paginated ``list_runs_enriched`` result envelope."""

    items: list[PaginatedRunItem]
    total: int
    offset: int
    limit: int
    has_more: bool


class McpServerHealthDict(TypedDict):
    """One MCP server's health, as produced by ``ServerHealth.to_dict``."""

    status: str
    tool_count: int
    fetched_at: NotRequired[str]
    last_error: NotRequired[str]


class McpHealthReportDict(TypedDict):
    """Aggregate MCP health, as produced by ``McpHealthReport.to_dict``."""

    status: str
    mcp_servers: dict[str, McpServerHealthDict]


class SkillMetadata(TypedDict, total=False):
    """Skill resource metadata.

    Known fields: skill_name (str). The structure may expand.
    """

    skill_name: str


class BindingDict(TypedDict):
    """A ``ResolvedBinding`` projected to the dict the materializer consumes."""

    binding_id: str
    resource_id: str
    version_id: str
    content_hash: str
    type: str
    slug: str
    display_name: str
    target_path: str | None
    materialize_mode: str
    on_conflict: str
    blobs: list[ResourceBlobRow]
    skill_meta: SkillMetadata | None
    source_metadata: SourceMetadata


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


class GrantParam(TypedDict, total=False):
    """One parameter descriptor in a capability's ``grant_schema``.

    NB: this is the codebase's own ``{"type": "int", "required": True,
    "default": …}`` descriptor shape — NOT a JSON Schema (the type system
    caught the difference). ``type`` is a Python-ish type name string.
    """

    type: str
    required: bool
    default: RawJsonValue


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
    # Provider-specific body passthrough (pydantic-ai ``extra_body``), e.g.
    # {"reasoning_effort": "none"} to disable qwen3 thinking loops. run_direct
    # forwards this into model_settings; without it here the schema strips it.
    # KEEP: arbitrary provider-specific JSON passthrough; schema varies by provider.
    extra_body: dict[str, RawJsonValue]


class ExecutionSection(TypedDict):
    """``config_json["execution"]`` — see ``build_config_json_payload()``."""

    max_validation_retries: int
    max_error_retries: int
    output_validation_engine: str


class RuntimeSection(TypedDict):
    """``config_json["runtime"]``."""

    mcp_config_path: str | None
    allowed_tools: list[str]
    forbidden_tools: list[str]


class ToolInfo(TypedDict):
    """One tool available (or effective) for an agent on a workspace.

    ``name`` is the canonical name for built-ins (``fs.read``) or the raw
    tool name for MCP/resource tools. ``source`` is where it comes from.
    ``native`` is the target engine's native name when known (built-ins
    only; ``None`` for MCP/resource tools whose name is already native).
    """

    name: str
    source: str  # "builtin" | "mcp" | "host_env" | "resource"
    native: str | None


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
    """Return shape of ``WorkspaceService.resolve_agent_host_env()``."""

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


# ── Intrinsic MCP servers: host-env tool results + stdio spawn spec ──────────
# (consumed by core/tools/mcp_servers — kept here on the data leaf so tools
# stays workspace-clean.)


class WorkspaceInfoResult(TypedDict):
    """agentbox.workspace_info tool result."""

    workspace_id: str
    run_id: str
    workdir: str


class ShellExecResult(TypedDict):
    """shell.exec tool result."""

    returncode: int
    stdout: str
    stderr: str


class HttpFetchResult(TypedDict):
    """http.fetch tool result."""

    status: int
    body: str


class McpServerEnv(TypedDict):
    """Environment variables for a stdio MCP server."""

    AGENTBOX_HOST_ENV_GRANTS_JSON: NotRequired[str]
    AGENTBOX_HOST_ENV_WORKSPACE_ID: NotRequired[str]
    AGENTBOX_HOST_ENV_WORKDIR: NotRequired[str]
    AGENTBOX_AGENT_TOOLS_GRANTS_JSON: NotRequired[str]
    AGENTBOX_AGENT_TOOLS_AGENT_ID: NotRequired[str]
    AGENTBOX_AGENT_TOOLS_RUN_ID: NotRequired[str]
    AGENTBOX_AGENT_TOOLS_WORKDIR: NotRequired[str]
    AGENTBOX_DB_PATH: str


class McpStdioServerSpec(TypedDict):
    """Stdio MCP server spawn specification (written into ``.mcp.json``)."""

    command: str
    args: list[str]
    env: McpServerEnv


__all__ = [
    "HttpFetchResult",
    "McpServerEnv",
    "McpStdioServerSpec",
    "ShellExecResult",
    "WorkspaceInfoResult",
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
    "SchemaSlotView",
    "SchemaValidationErrorView",
    "ScriptSampleValidationResult",
    "ScriptValidatorView",
    "SkillBindingsResult",
    "SkillCatalogItem",
    "SkillMetadata",
    "SnapshotEntryView",
    "UsagePayload",
    "AgentValidationResult",
    "LogEntry",
    "PromptFragmentPayload",
    "PromptVersionDetail",
    "PromptVersionListResult",
    "PromptVersionSummary",
    "ResourceListResult",
    "RunCommentsResult",
    "RunDetailPayload",
    "RunDetailResult",
    "RunFacetsResult",
    "RunLogsResult",
    "RunPromptFragmentsResult",
    "PaginatedRunItem",
    "PaginatedRunsResult",
    "ValidationView",
    "WebhookChannelConfig",
    "WorkspaceBindingItemsResult",
    "WorkspaceBindingSpec",
    "WorkspaceResourcesResult",
]
