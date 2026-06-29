"""Agent definition models loaded from agentbox.toml."""

from __future__ import annotations

import contextlib
import enum
import json as _json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from agentbox.core.constants import SessionMode
from agentbox.core.data.manifests.engines import RunnerManifest, RunnerSpec
from agentbox.core.data.rows import AgentVersionRow


class AgentSource(enum.StrEnum):
    """Format and location of an agent definition's source file."""

    INLINE_TOML = "inline_toml"
    """Agent defined as an ``[[agents]]`` block inside ``agentbox.toml``."""
    STANDALONE_TOML = "standalone_toml"
    """Agent defined in a separate ``.toml`` file under ``agents.d/``."""
    MARKDOWN = "markdown"
    """Agent defined as a markdown file with YAML frontmatter under ``agents.d/``."""
    LEGACY_DIR = "legacy_dir"
    """Agent defined via the legacy ``agents/<name>/agent.toml`` + ``prompts/system.md`` pattern."""
    BUNDLE = "bundle"
    """Agent defined as a bundle directory: ``<bundle_dir>/<id>/agent.toml`` with
    a ``[composition]`` block declaring system prompt, references, and schemas."""


class SharedRef(BaseModel):
    """Reference to a shared resource (versioned, stored in DB).

    When used in composition references, system prompt, or schemas, the
    shared resource is resolved at run time via SessionStore.
    """

    shared: str
    """Resource id, e.g. 'schema/job-eval-v3', 'guideline/resume-rules'."""

    version: int | None = None
    """Optional specific version; None = use active version."""

    model_config = ConfigDict(extra="forbid")


class CompositionConfig(BaseModel):
    """Prompt-composition recipe for an agent bundle.

    When present, agentbox owns prompt rendering via
    ``agentbox.core.agents.composition.bundle.compose()``.

    Supports both filesystem paths and shared resource references:
    - File paths: ``"prompts/system.md"`` or ``"shared://root/path.md"``
    - Shared refs: ``{"shared": "resource-id", "version": 2}`` (version optional)
    """

    system: str | SharedRef = "prompts/system.md"
    """System prompt: bundle-relative path, shared:// path, or SharedRef."""

    references: list[str | dict | SharedRef] = Field(default_factory=list)
    """Reference files. Each entry can be a path string, a dict with ``path``
    and optional ``heading``, or a SharedRef."""

    user_template: str | SharedRef | None = None
    """User template: path string or SharedRef. When unset,
    ``variables["user_message"]`` is used verbatim."""

    input_schema: str | SharedRef | None = None
    """Input schema: path string or SharedRef."""

    output_schema: str | SharedRef | None = None
    """Output schema: path string or SharedRef."""

    transport: str = "system_message"
    """How the composed system prompt is delivered to the runner.
    E.g. ``system_message``, ``file`` (CLAUDE.md), etc."""

    output_validation: str = "strict"
    """One of ``strict`` | ``warn`` | ``off``."""


class AgentDef(BaseModel):
    id: str
    """Stable identifier (e.g. `myproject.draft_writer`)."""

    description: str = ""
    prompt_path: str | None = None
    """Project-relative path to system prompt markdown.

    For ``token`` runners without an explicit ``agent_module``,
    this markdown is used to auto-generate a minimal agent.

    .. deprecated::
       Use ``[composition]`` instead.
    """

    prompt: str | None = None
    """Inline system prompt text. Mutually exclusive with ``prompt_path`` —
    when both are set, ``prompt`` wins."""

    composition: CompositionConfig | None = None
    """Prompt-composition recipe. When present, takes precedence over
    ``prompt_path`` / ``prompt``."""

    workspace: str | None = None
    """Workspace reference.

    Resolution:
    - Named workspace: "default", "research" (looked up in workspaces table)
    - Explicit path: "workdir/agentbox/ws/foo"
    - "<ephemeral>": fresh tmp dir per run, deleted after (sandbox mode).
    - Omitted: auto-resolved to ``<workspaces_root>/<agent_id>/``.
    """

    runner: RunnerSpec = Field(default_factory=lambda: RunnerSpec())
    session_mode: SessionMode = SessionMode.HEADLESS
    tags: list[str] = Field(default_factory=list)

    unsupported_backends: list[str] = Field(default_factory=list)
    """Backend names that this agent cannot run on. When set, those
    backends are skipped during automatic backend selection (see
    ``backend_preference`` on ``ProjectManifest``)."""

    claude_agent: bool = True
    """False means pydantic-only — no external Claude/OpenCode config."""

    headless: bool = False
    """True means no interactive tools — the agent receives the prompt via
    stdin and emits JSON to stdout."""

    tools: list[str] = Field(default_factory=list)
    """Tool names / ``@group`` references for the Claude/OpenCode agent profile."""

    webhook_url: str | None = None
    """Optional URL agentbox POSTs to when a run for this agent reaches a
    terminal state (ok/error). Body: {run_id, agent_id, status, output,
    error, started_at, finished_at, usage, duration_ms}. Failures are
    retried a few times then logged.

    If unset, falls back to Settings.completion_webhook_url (env var
    AGENTBOX_COMPLETION_WEBHOOK_URL). Set to empty string to opt out when
    a global default is configured."""

    source_path: Path | None = None
    """Absolute path to the source file this agent was loaded from.

    Used by ``ManifestWriter`` to dispatch to the correct writer.
    Set automatically by ``DefinitionLoader``; *None* for agents
    created programmatically without a backing file.
    """

    source_format: AgentSource | None = None
    """Format of the source file (inline TOML, standalone TOML, markdown).

    Set automatically by ``DefinitionLoader``; *None* for agents
    created programmatically.
    """

    def load_prompt(self, project_root: Path) -> str:
        if self.prompt:
            return self.prompt
        if self.prompt_path:
            return (project_root / self.prompt_path).read_text(encoding="utf-8")
        return ""

    @classmethod
    def from_db_row(cls, row: AgentVersionRow | dict) -> AgentDef:
        """Reconstruct an ``AgentDef`` from a stored ``agent_versions`` row.

        Prefers the ``config_json`` column (the DB-as-source-of-truth
        snapshot); falls back to ``content_snapshot`` for legacy rows.
        Missing rows raise ``ValueError``.
        """
        raw = row.get("config_json") or row.get("content_snapshot")
        if raw is None:
            raise ValueError("agent_versions row has no config payload")
        data = _json.loads(raw) if isinstance(raw, str) else raw
        inst = cls.model_validate(data)
        # Stash the structured config_json so the agent_config
        # accessors (ExecutionConfig/RuntimeConfig/PythonAgentConfig)
        # can read execution/runtime/python sub-dicts directly without
        # roundtripping through the legacy agent.runner pydantic model.
        # Falls back to the same data dict when config_json was absent —
        # the accessors only consume sub-keys they recognize.
        with contextlib.suppress(Exception):
            object.__setattr__(inst, "_config_json", data)
        return inst


class AgentManifest(BaseModel):
    """Per-agent metadata, read from ``<agents_dir>/<name>/agent.toml``."""

    id: str
    """Agent identifier (must match the directory name)."""

    description: str = ""
    prompt_path: str | None = None
    """Path inside the agent directory to the system prompt markdown.

    Resolved relative to the agent directory. When omitted, falls back to
    ``prompts/system.md`` if that file exists; otherwise no prompt is set.

    .. deprecated::
       Use ``[composition]`` instead.
    """

    composition: CompositionConfig | None = None
    """Prompt-composition recipe. When present, takes precedence."""

    workspace: str | None = None
    session_mode: SessionMode = SessionMode.HEADLESS
    webhook_url: str | None = None
    tags: list[str] = Field(default_factory=list)

    runner: RunnerManifest | None = None
    """Runner configuration. When unset, a default ``token``
    runner is used (auto-generated agent from the markdown prompt)."""
