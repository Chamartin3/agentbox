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
    RepoResourceRow,
    ResourceBlobRow,
    ResourceVersionRow,
    WorkspaceFileBindingRow,
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


class NotFoundResult(TypedDict):
    """Standard MCP tool error: requested resource was not found."""

    error: str
    run_id: str


class BackendLabelsDict(TypedDict):
    """Mapping from every known ``BackendName`` to its display label."""

    claude_code: str
    opencode: str
    codex: str
    pi: str
    token: str


class BackendToRunnerDict(TypedDict):
    """Mapping from every known ``BackendName`` to its ``RunnerKind`` string."""

    claude_code: str
    opencode: str
    codex: str
    pi: str
    token: str


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
    references: list[dict[str, str]]
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


__all__ = [
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
    "ValidationView",
    "WebhookChannelConfig",
    "WorkspaceBindingItemsResult",
    "WorkspaceBindingSpec",
    "WorkspaceResourcesResult",
]
