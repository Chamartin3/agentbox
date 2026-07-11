"""Logic-free shapes for agent composition, prompts, and validation.

Shapes that cross the agents-domain boundary and are needed by execution,
observability, or other core layers. These are moved from agents submodules
to enable those packages to import typed composition/validation results
without creating circular dependencies or importing the agents domain.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from agentbox.core.data.payload_types import (
    JsonSchemaDict,
    PromptEmbedSnapshotEntry,
    ResolvedBindingView,
)
from agentbox.core.data.manifests.agents import AgentDef


# ──────────────────────────────────────────────────────────────────────────
# Composition bundle shapes (from core/agents/composition/bundle/compose.py)
# ──────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ComposedReference:
    """One reference section as composed (raw, rendered text)."""

    path: str
    heading: str
    content: str


@dataclass(frozen=True)
class ComposeResult:
    """Result of composing a prompt bundle.

    ``system`` is the fully-composed system prompt (base + input schema
    block + references + output schema block) — what file-based backends
    (claude_code, opencode, codex, pi) need.

    ``system_base`` is the raw rendered system prompt **without** the
    auto-appended schema/reference blocks. The token backend uses this
    because pydantic-ai injects its own schema description and the
    reference content goes via deps; appending the schema again would
    duplicate (and potentially conflict with) what pydantic-ai sends.

    ``references`` and ``input_schema`` are likewise the structured
    pieces, available so backends can route them to native channels
    instead of string-concatenation.
    """

    system: str
    user: str
    schema: JsonSchemaDict | None
    schema_sha: str | None
    bundle_sha: str
    system_base: str = ""
    references: tuple[ComposedReference, ...] = ()
    input_schema: JsonSchemaDict | None = None


# ──────────────────────────────────────────────────────────────────────────
# Prompt resolution shapes (from core/agents/composition/resolver.py)
# ──────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ResolvedBinding:
    binding_id: str
    marker: str
    resource_id: str
    version_id: str
    content_hash: str
    type: str
    mode: str
    rendered: str
    required: bool


@dataclass(frozen=True)
class PromptResolution:
    rendered_prompt: str
    snapshot: list[ResolvedBinding]
    unresolved_markers: list[str]
    warnings: list[str]


# ──────────────────────────────────────────────────────────────────────────
# Fragment shapes (from core/agents/composition/capture.py)
# ──────────────────────────────────────────────────────────────────────────


@dataclass
class PromptFragment:
    name: str
    """Short label, e.g. 'user_input', 'agent_system_prompt'."""

    source: str
    """'user', 'agent_def', 'project', 'agentbox', 'claude_cli'."""

    injected_by: str
    """Which layer pushes this text into the model: 'agentbox', 'claude_cli', 'token'."""

    content: str
    """The actual text. May be a note for things we cannot inspect."""

    inspectable: bool = True
    """False = we describe what's there but don't have the bytes (e.g. Claude CLI envelope)."""

    shared_resource_id: str | None = None
    """Optional: id of the shared resource this fragment came from."""

    shared_resource_version: int | None = None
    """Optional: version of the shared resource (None = active version was used)."""

    @property
    def size_bytes(self) -> int:
        return len(self.content.encode("utf-8"))


# ──────────────────────────────────────────────────────────────────────────
# Validation shapes (from core/agents/validation/schema.py)
# ──────────────────────────────────────────────────────────────────────────

# Engine label for the validator that produced the verdict. ``off`` means
# no schema is configured and validation was skipped; ``none`` means a
# schema was expected but the input was unrunnable (empty / unparseable).
ValidationEngine = Literal[
    "jsonschema",
    "pydantic",
    "both",
    "json-schema",
    "http-callback",
    "script",
    "json-schema+http-callback",
    "json-schema+script",
    "none",
    "off",
]


@dataclass(frozen=True)
class HttpValidatorConfig:
    """HTTP callback validator — POSTs output, expects {ok, error}.

    ``description`` is the human-readable constraint this validator
    enforces. It's rendered into the system prompt as a bullet under
    ``## Constraints`` so the model sees both the rule and knows it's
    enforced. Validators own their constraint text.
    """

    kind: Literal["http"] = "http"
    endpoint: str = ""
    timeout_seconds: int = 5
    description: str = ""


@dataclass(frozen=True)
class ScriptValidatorConfig:
    """Python script validator — runs operator-uploaded code in-process.

    The script (loaded from a versioned ``repo_resource`` of type
    ``'script'``) must define::

        def validate(output: str) -> dict:
            # return {"ok": True} or {"ok": False, "error": "..."}

    Resolved upstream by ``resolve_output_config`` so the runtime
    receives the source code directly and does not need DB access.

    ``description`` mirrors ``HttpValidatorConfig.description`` —
    human-readable constraint text rendered into the system prompt.
    """

    kind: Literal["script"] = "script"
    resource_id: str = ""
    resource_version_id: str | None = None
    source_code: str = ""
    description: str = ""


# Discriminated union — extend by adding a new dataclass + a kind
# branch in resolve_output_config + a dispatch in core/run/validation.
ValidatorConfig = HttpValidatorConfig | ScriptValidatorConfig


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of validating a backend run's output.

    ``ok=True, engine="off"`` is the no-schema-configured case — the
    executor should treat it as "validation skipped", not "passed".
    """

    ok: bool
    error: str = ""
    engine: ValidationEngine = "off"


# ──────────────────────────────────────────────────────────────────────────
# Runtime shapes (from core/agents/runtime.py)
# ──────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AgentRuntimeView:
    """Execution's typed view of per-run agent configuration.

    Built once by the Agents domain; consumed by the executor, step-loop,
    and validation.  No execution code should call ``.from_agent()``
    directly — the compose-prompt facade returns this as part of
    :class:`ComposedPrompt`.
    """

    max_validation_retries: int = 0
    max_error_retries: int = 0
    output_validation_engine: str = "both"
    output_schema_path: str | None = None
    json_schema: JsonSchemaDict | None = None
    validators: tuple[ValidatorConfig, ...] = ()

    @property
    def has_schema(self) -> bool:
        return (
            self.output_schema_path is not None
            or self.json_schema is not None
            or bool(self.validators)
        )


@dataclass(frozen=True)
class ComposedState:
    """Composed-prompt state for one run — the backend-facing view.

    Single typed replacement for the seven ``agent.__dict__["_composed_*"]``
    keys the executor and backends used to share. Produced by
    :meth:`ComposedPrompt.to_composed_state` and threaded explicitly through
    render / validate / capture so no hidden side-channel survives on the
    AgentDef.

    All fields are optional; ``None`` means "this aspect wasn't composed
    for this run." Backends should treat a missing ``ComposedState`` (or
    one with ``system is None``) as "no composition — fall back to the
    agent's inline prompt and on-disk files."
    """

    system: str | None = None
    system_base: str | None = None
    schema: JsonSchemaDict | None = None
    input_schema: JsonSchemaDict | None = None
    user: str | None = None
    references: tuple[ComposedReference, ...] | None = None
    bundle_sha: str | None = None
    validation_mode: str | None = None


@dataclass(frozen=True)
class ComposedPrompt:
    """Composed prompt state produced by ``build_prompt()``.

    Contains everything the executor needs from the composition
    pipeline: prompt texts, schemas, validation hints, and the
    agent's runtime view. Composition is the agents domain's job — the
    executor consumes this shape and never assembles a prompt itself.
    """

    system_text: str | None = None
    system_base: str | None = None
    composed_schema: JsonSchemaDict | None = None
    composed_input_schema: JsonSchemaDict | None = None
    composed_user: str | None = None
    agent: AgentDef | None = None
    input_: str = ""
    composed_references: tuple[ComposedReference, ...] | None = None
    composed_bundle_sha: str | None = None
    validation_mode: str | None = None
    composition_result: ComposeResult | None = None
    prompt_bindings: list[ResolvedBindingView] = field(default_factory=list)
    snapshot_entries: list[PromptEmbedSnapshotEntry] = field(default_factory=list)
    runtime_view: AgentRuntimeView | None = None

    def to_composed_state(self) -> ComposedState:
        """Project the backend-facing subset of the composed prompt."""
        return ComposedState(
            system=self.system_text,
            system_base=self.system_base,
            schema=self.composed_schema,
            input_schema=self.composed_input_schema,
            user=self.composed_user,
            references=self.composed_references,
            bundle_sha=self.composed_bundle_sha,
            validation_mode=self.validation_mode,
        )


@dataclass(frozen=True)
class RunSpec:
    """Execution's input contract for a single run.

    The prompt is composed ONCE at run creation (the service layer), never
    rebuilt by the executor: a run queued before an agent edit executes the
    prompt composed at creation. ``RunSpec`` bundles that composed prompt with
    the dispatch statics the executor resolves as the run begins, so execution
    only drives the engine, enforces the contract, and retries within budget.
    """

    composed: ComposedPrompt
    engine_name: str
    input_: str
    workdir: Path
    timeout_seconds: int


__all__ = [
    "AgentRuntimeView",
    "ComposedPrompt",
    "ComposedReference",
    "ComposedState",
    "RunSpec",
    "ComposeResult",
    "HttpValidatorConfig",
    "PromptFragment",
    "PromptResolution",
    "ResolvedBinding",
    "ScriptValidatorConfig",
    "ValidationEngine",
    "ValidationResult",
    "ValidatorConfig",
]
