"""System domain service payloads — TypedDicts for configuration and credentials."""

from __future__ import annotations

from typing import Literal, TypedDict


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


class HttpValidatorView(TypedDict):
    kind: Literal["http"]
    endpoint: str
    timeout_seconds: int
    description: str


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


class NotFoundResult(TypedDict):
    """Standard MCP tool error: requested resource was not found."""

    error: str
    run_id: str


class RefSection(TypedDict):
    """Rendered reference section — one file's content with its heading."""

    heading: str
    content: str


class RefreshProvidersResult(TypedDict):
    """Return shape of ``refresh_providers()``."""

    opencode: list[str]
    opencode_count: int
    model_cache_cleared: bool


class ScriptSampleValidationResult(TypedDict):
    """Return shape of ``ResourceService.validate_script_sample()``."""

    valid: bool
    errors: list
    schema_resource_id: str


class ScriptValidatorView(TypedDict):
    kind: Literal["script"]
    resource_id: str
    resource_slug: str | None
    resource_display_name: str | None
    pinned_version_id: str | None
    description: str


class StubResult(TypedDict):
    """Ungranted-tool stub return — placeholder until the user grants access."""

    error: str
    tool: str


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
