"""Load agent definitions from the project volume.

Two sources, merged:

1. **Inline** — ``[[agents]]`` blocks in ``agentbox.toml``.
   For backwards compatibility. These take precedence when an agent ID
   exists in both sources.

2. **Directory** — a bound agents directory (default ``agents/`` at
   project root). Each subdirectory with an ``agent.toml`` file is an
   agent. The ``agent.toml`` declares metadata and a ``[runner]`` spec.

   For markdown-only agents, just add ``prompts/system.md`` — the
   ``agent.toml`` can omit the runner kind and a ``pydantic_ai`` runner
   with auto-generated agent is used by default.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from agentbox.core.constants import RunnerKind, SessionMode

from .models import AgentDef, RunnerSpec, WorkspaceDef


McpTransport = Literal["http", "sse"]


class ProjectManifest(BaseModel):
    project: str = "default"
    agents_dir: str = "agents"
    """Project-relative path to the bound agents directory.

    Agentbox scans this directory for subdirectories containing
    ``agent.toml`` files and registers each as an agent.
    """

    agents: list[AgentDef] = Field(default_factory=list)
    """Inline agent definitions (``[[agents]]`` in agentbox.toml).

    These are merged with directory-discovered agents; inline takes
    precedence when IDs collide.
    """

    workspaces: list[WorkspaceDef] = Field(default_factory=list)
    """Named workspace definitions (``[[workspaces]]`` in agentbox.toml)."""

    mcp_server_name: str = "mcp"
    """MCP server name used in generated configs (e.g. ``mcp__<name>__tool``)."""

    mcp_command: list[str] = Field(default_factory=lambda: ["mcp_serve.sh"])
    """Command array for the MCP server (stdio transport). Used when
    ``mcp_url`` is not set."""

    mcp_url: str | None = None
    """HTTP/SSE endpoint for a remote MCP server (e.g.
    ``http://cvagents-mcp:8001/mcp/``). When set, generated configs use
    a remote MCP entry and ``mcp_command`` is ignored."""

    mcp_transport: McpTransport = "http"
    """Transport for the remote MCP server. Only consulted when
    ``mcp_url`` is set."""

    tool_manifest_path: str = "bin/_generated/tool_manifest.json"
    """Project-relative path to the tool manifest JSON."""


class AgentManifest(BaseModel):
    """Per-agent metadata, read from ``<agents_dir>/<name>/agent.toml``."""

    id: str
    """Agent identifier (must match the directory name)."""

    description: str = ""
    prompt_path: str | None = None
    """Path inside the agent directory to the system prompt markdown.

    Resolved relative to the agent directory. When omitted, falls back to
    ``prompts/system.md`` if that file exists; otherwise no prompt is set.
    """

    workspace: str | None = None
    session_mode: SessionMode = "headless"
    webhook_url: str | None = None
    tags: list[str] = Field(default_factory=list)

    runner: RunnerManifest | None = None
    """Runner configuration. When unset, a default ``pydantic_ai``
    runner is used (auto-generated agent from the markdown prompt)."""


class RunnerManifest(BaseModel):
    """Per-agent runner config, a subset of RunnerSpec for the TOML file.

    Workspace-generated configs (agents.json, settings.json, opencode.json)
    are resolved automatically from the workspace directory at runtime and
    do not appear here.
    """

    kind: RunnerKind = RunnerKind.PYDANTIC_AI
    """Defaults to ``pydantic_ai`` so markdown-only agents need no
    explicit runner configuration."""

    model: str | None = None
    agent_module: str | None = None
    """Python import path for pydantic_ai agents
    (e.g. ``agents.company_researcher.agent:CompanyResearcherAgent``)."""

    mcp_config_path: str | None = None
    """Global MCP server configuration, resolved relative to project root."""

    allowed_tools: list[str] = Field(default_factory=list)
    extra_args: list[str] = Field(default_factory=list)
    timeout_seconds: int = 120

    output_schema_path: str | None = None
    max_validation_retries: int = 0


class DefinitionLoader:
    """Loads agent definitions from ``agentbox.toml`` + agents directory."""

    def __init__(self, project_root: Path):
        self.project_root = project_root

    @property
    def manifest_path(self) -> Path:
        return self.project_root / "agentbox.toml"

    def load(self) -> ProjectManifest:
        manifest = self._load_toml()
        dir_agents = self._load_directory_agents(manifest.agents_dir)

        # Merge: inline agents take precedence over directory agents.
        merged = {a.id: a for a in dir_agents}
        for a in manifest.agents:
            merged[a.id] = a

        manifest.agents = list(merged.values())
        return manifest

    def get(self, agent_id: str) -> AgentDef | None:
        for a in self.load().agents:
            if a.id == agent_id:
                return a
        return None

    def get_workspace(self, name: str) -> WorkspaceDef | None:
        for w in self.load().workspaces:
            if w.name == name:
                return w
        return None

    def list_workspaces(self) -> list[WorkspaceDef]:
        return list(self.load().workspaces)

    # ------------------------------------------------------------------
    # TOML loader
    # ------------------------------------------------------------------

    def _load_toml(self) -> ProjectManifest:
        if not self.manifest_path.exists():
            return ProjectManifest()
        with self.manifest_path.open("rb") as f:
            data = tomllib.load(f)
        return ProjectManifest.model_validate(data)

    # ------------------------------------------------------------------
    # Directory-based agent discovery
    # ------------------------------------------------------------------

    def _load_directory_agents(self, agents_dir: str) -> list[AgentDef]:
        """Scan ``<project_root>/<agents_dir>/`` for agent subdirectories."""
        root = self.project_root / agents_dir
        if not root.is_dir():
            return []

        agents: list[AgentDef] = []
        for entry in sorted(root.iterdir()):
            if not entry.is_dir():
                continue
            agent = self._load_agent_from_dir(entry)
            if agent is not None:
                agents.append(agent)
        return agents

    def _load_agent_from_dir(self, agent_dir: Path) -> AgentDef | None:
        """Read ``agent.toml`` from ``agent_dir`` and return an ``AgentDef``.

        Three cases:

        1. ``agent.toml`` exists → full configuration from the manifest.
        2. No ``agent.toml``, but ``prompts/system.md`` exists → auto-generate
           a minimal pydantic_ai agent with defaults.
        3. Neither → skip (not an agent directory).
        """
        manifest_path = agent_dir / "agent.toml"

        if manifest_path.exists():
            return self._build_from_manifest(manifest_path, agent_dir)

        # No agent.toml — check for markdown-only agent.
        # Agents without explicit workspace use the "default" named workspace.
        prompt_path = agent_dir / "prompts" / "system.md"
        if prompt_path.exists():
            return AgentDef(
                id=agent_dir.name,
                description=f"Auto-discovered agent from {agent_dir.name}",
                prompt_path=str(prompt_path),
                workspace="default",
                runner=RunnerSpec(
                    kind=RunnerKind.PYDANTIC_AI,
                    timeout_seconds=120,
                ),
            )

        return None

    def _build_from_manifest(
        self, manifest_path: Path, agent_dir: Path
    ) -> AgentDef:
        """Parse an ``agent.toml`` file into an ``AgentDef``."""
        with manifest_path.open("rb") as f:
            data = tomllib.load(f)
        manifest = AgentManifest.model_validate(data)

        # Resolve prompt_path relative to the agent directory.
        if manifest.prompt_path is not None:
            resolved_prompt: str | None = str((agent_dir / manifest.prompt_path).resolve())
        else:
            default = agent_dir / "prompts" / "system.md"
            resolved_prompt = str(default) if default.exists() else None

        # Build RunnerSpec from the manifest (or use defaults).
        if manifest.runner is None:
            runner_spec = RunnerSpec(
                kind=RunnerKind.PYDANTIC_AI,
                timeout_seconds=120,
            )
        else:
            rm = manifest.runner
            runner_spec = RunnerSpec(
                kind=rm.kind,
                model=rm.model,
                mcp_config_path=rm.mcp_config_path,
                allowed_tools=rm.allowed_tools,
                extra_args=rm.extra_args,
                timeout_seconds=rm.timeout_seconds,
                agent_module=rm.agent_module,
                output_schema_path=rm.output_schema_path,
                max_validation_retries=rm.max_validation_retries,
            )

        # Use "default" workspace when not explicitly set.
        return AgentDef(
            id=manifest.id,
            description=manifest.description,
            prompt_path=resolved_prompt,
            workspace=manifest.workspace or "default",
            session_mode=manifest.session_mode,
            webhook_url=manifest.webhook_url,
            tags=manifest.tags,
            runner=runner_spec,
        )
