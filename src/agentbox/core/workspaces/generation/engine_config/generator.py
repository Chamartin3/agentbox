"""ConfigGenerator — drives per-workspace runner config generation."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Final, Protocol

from agentbox.config import Settings

from ._common import _dump_json, _materialize_workspace_files
from .claude_agents import build_claude_agents
from .claude_mcp import build_claude_mcp_config
from .claude_settings import build_claude_settings
from .discovery import AgentDiscovery, DiscoveredAgent
from .opencode_config import build_opencode_config
from .schemas.claude import ClaudeSettingsConfig
from .schemas.opencode import OpenCodeConfig

if TYPE_CHECKING:
    from agentbox.core.workspaces.mcp.client import McpToolManifest


# ---------------------------------------------------------------------------
# Writer types — inlined from the former writers.py module
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WriteContext:
    """Per-run configuration the writers consume.

    Held in a single object so adding a new field (extra MCP transport,
    feature flag, etc.) does not change every writer's signature.
    """

    allowed_builtin: list[str] | None
    mcp_server_name: str
    mcp_command: list[str]
    mcp_url: str | None
    mcp_transport: str
    servers: list[dict] | None
    claude_mcp_prefix: str


@dataclass(frozen=True)
class WriteResult:
    """What one writer produced.

    ``summary`` is a one-line message for verbose-mode UIs; ``None`` if
    the writer has nothing interesting to say.
    """

    key: str
    path: Path
    summary: str | None = None


class ConfigWriter(Protocol):
    """Writes one config file for one backend.

    ``key`` matches the keys ``ConfigGenerator`` returns in its path
    map (``claude_agents``, ``opencode``, …) so adding a writer
    automatically extends the public surface.
    """

    key: ClassVar[str]
    filename: ClassVar[str]

    def write(
        self,
        target_dir: Path,
        agents: list[DiscoveredAgent],
        ctx: WriteContext,
    ) -> WriteResult: ...


class ClaudeAgentsWriter:
    """Emits ``claude_agents.json`` (Claude Code agent table)."""

    key: ClassVar[str] = "claude_agents"
    filename: ClassVar[str] = "claude_agents.json"

    def write(
        self,
        target_dir: Path,
        agents: list[DiscoveredAgent],
        ctx: WriteContext,
    ) -> WriteResult:
        data = build_claude_agents(agents)
        path = _dump_json(target_dir / self.filename, data)
        return WriteResult(
            key=self.key,
            path=path,
            summary=f"  Wrote {len(data)} agents to {path}",
        )


class ClaudeSettingsWriter:
    """Emits ``claude_settings.json`` (Claude permission allow/deny)."""

    key: ClassVar[str] = "claude_settings"
    filename: ClassVar[str] = "claude_settings.json"

    def write(
        self,
        target_dir: Path,
        agents: list[DiscoveredAgent],
        ctx: WriteContext,
    ) -> WriteResult:
        data = build_claude_settings(
            agents, ctx.allowed_builtin, ctx.claude_mcp_prefix
        )
        path = _dump_json(target_dir / self.filename, data)
        cfg = ClaudeSettingsConfig.model_validate(data)
        allow_count = len(cfg.permissions.allow)
        return WriteResult(
            key=self.key,
            path=path,
            summary=f"  Wrote {allow_count} permissions to {path}",
        )


class ClaudeMcpWriter:
    """Emits ``claude_mcp.json`` (Claude ``--mcp-config`` payload)."""

    key: ClassVar[str] = "claude_mcp"
    filename: ClassVar[str] = "claude_mcp.json"

    def write(
        self,
        target_dir: Path,
        agents: list[DiscoveredAgent],
        ctx: WriteContext,
    ) -> WriteResult:
        data = build_claude_mcp_config(
            servers=ctx.servers,
            mcp_server_name=ctx.mcp_server_name,
            mcp_url=ctx.mcp_url,
            mcp_transport=ctx.mcp_transport,
            mcp_command=ctx.mcp_command,
        )
        path = _dump_json(target_dir / self.filename, data)
        kind = "remote" if ctx.mcp_url else "stdio"
        return WriteResult(
            key=self.key,
            path=path,
            summary=f"  Wrote {kind} Claude MCP config to {path}",
        )


class OpenCodeWriter:
    """Emits ``opencode.json`` (OpenCode agent + permission table)."""

    key: ClassVar[str] = "opencode"
    filename: ClassVar[str] = "opencode.json"

    def write(
        self,
        target_dir: Path,
        agents: list[DiscoveredAgent],
        ctx: WriteContext,
    ) -> WriteResult:
        data = build_opencode_config(
            agents,
            mcp_server_name=ctx.mcp_server_name,
            mcp_command=ctx.mcp_command,
            mcp_url=ctx.mcp_url,
            mcp_transport=ctx.mcp_transport,
            servers=ctx.servers,
        )
        path = _dump_json(target_dir / self.filename, data)
        cfg = OpenCodeConfig.model_validate(data)
        enabled = [k for k, v in cfg.agent.items() if not v.disable]
        return WriteResult(
            key=self.key,
            path=path,
            summary=f"  Wrote {len(enabled)} opencode agents to {path}",
        )


DEFAULT_WRITERS: Final[tuple[ConfigWriter, ...]] = (
    ClaudeAgentsWriter(),
    ClaudeSettingsWriter(),
    ClaudeMcpWriter(),
    OpenCodeWriter(),
)


# ---------------------------------------------------------------------------
# ConfigGenerator
# ---------------------------------------------------------------------------


class ConfigGenerator:
    """Generates runner configuration files for a workspace.

    Parameters
    ----------
    agentbox_toml:
        Path to agentbox.toml (single source of truth).
    manifest_path:
        Legacy path to tool_manifest.json (deprecated).
    mcp_manifest:
        Runtime MCP tool manifest (preferred over manifest_path).
    mcp_server_name:
        MCP server name for OpenCode config.
    mcp_command:
        Command array for MCP server in OpenCode config.
    """

    def __init__(
        self,
        agentbox_toml: Path,
        manifest_path: Path | None = None,
        *,
        mcp_manifest: "McpToolManifest | None" = None,
        mcp_server_name: str = "mcp",
        mcp_command: list[str] | None = None,
        mcp_url: str | None = None,
        mcp_transport: str = "http",
        servers: list[dict] | None = None,
        verbose: bool = True,
        writers: Sequence[ConfigWriter] | None = None,
    ) -> None:
        self.discovery = AgentDiscovery(
            agentbox_toml=agentbox_toml,
            manifest_path=manifest_path,
            mcp_manifest=mcp_manifest,
            mcp_server_name=mcp_server_name,
            verbose=verbose,
        )
        self.mcp_server_name = mcp_server_name
        self.mcp_command = mcp_command or ["mcp_serve.sh"]
        self.mcp_url = mcp_url
        self.mcp_transport = mcp_transport
        self.servers = servers
        self.verbose = verbose
        # The writer list IS the backend set. Adding a third backend
        # (e.g. Codex) is a new ConfigWriter class plus passing it here.
        self.writers: tuple[ConfigWriter, ...] = (
            tuple(writers) if writers is not None else DEFAULT_WRITERS
        )

    def generate_for_workspace(
        self,
        workspace_path: Path,
        allowed_tools: set[str] | None = None,
        allowed_builtin_tools: list[str] | None = None,
        files: list[dict] | None = None,
        project_root: Path | None = None,
    ) -> dict[str, Path]:
        """Generate all configs into ``workspace_path/.agentbox/generated/``.

        ``allowed_tools`` (set of mcp-prefixed tool names) restricts each
        agent's tool list before generation. ``allowed_builtin_tools`` is
        forwarded into the Claude settings builder unchanged. Both Claude
        and OpenCode configs are generated from the same filtered shape.

        Also mirrors the Claude settings document to
        ``<workspace>/.claude/settings.json`` so Claude Code's CWD auto-load
        picks up the same deny/allow when an interactive launcher does not
        pass ``--settings`` explicitly. Declared workspace ``files`` are
        copied into the workspace cwd (not the generated subdir).
        """
        agents = self._filter_by_allowed(
            self.discovery.discover_mcp_agents(), allowed_tools
        )
        target_dir = workspace_path / ".agentbox" / "generated"
        paths = self._write_configs(
            target_dir, agents, allowed_builtin_tools, verbose=self.verbose,
        )
        if files and project_root is not None:
            _materialize_workspace_files(workspace_path, files, project_root)
        self._mirror_claude_settings(workspace_path, paths["claude_settings"])
        return paths

    def generate_configs_into(
        self,
        target_dir: Path,
        allowed_builtin_tools: list[str] | None = None,
        files: list[dict] | None = None,
        project_root: Path | None = None,
    ) -> dict[str, Path]:
        """Generate all configs as flat files into ``target_dir``.

        Unlike :meth:`generate_for_workspace` this writes directly to an
        arbitrary directory without a ``.agentbox/generated/`` subdirectory
        and emits no verbose progress lines. Declared workspace ``files``
        are copied into ``target_dir`` (flat). Used by the executor to
        populate per-run tmpfs directories.
        """
        agents = self.discovery.discover_mcp_agents()
        paths = self._write_configs(
            target_dir, agents, allowed_builtin_tools, verbose=False,
        )
        if files and project_root is not None:
            _materialize_workspace_files(target_dir, files, project_root)
        return paths

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _filter_by_allowed(
        self,
        agents: list[DiscoveredAgent],
        allowed_tools: set[str] | None,
    ) -> list[DiscoveredAgent]:
        """Keep only tools in ``allowed_tools``; drop agents left empty.

        ``None`` means "no filter" and returns the input unchanged.
        """
        if allowed_tools is None:
            return agents
        filtered: list[DiscoveredAgent] = []
        for agent in agents:
            kept = [t for t in agent["mcp_tools"] if t in allowed_tools]
            if not kept:
                continue
            narrowed: DiscoveredAgent = {**agent, "mcp_tools": kept}
            filtered.append(narrowed)
        if self.verbose:
            total = sum(len(a["mcp_tools"]) for a in filtered)
            print(f"  Filtered to {len(filtered)} agents with {total} allowed tools")
        return filtered

    def _write_configs(
        self,
        target_dir: Path,
        agents: list[DiscoveredAgent],
        allowed_builtin: list[str] | None,
        *,
        verbose: bool,
    ) -> dict[str, Path]:
        """Drive every registered :class:`ConfigWriter` against ``target_dir``.

        Returns the path map both public methods exposed before the
        Protocol introduction — same keys, same files, byte-identical
        content. File materialization and the ``.claude/settings.json``
        mirror are callers' responsibilities because they target
        different paths in the workspace and executor forms.
        """
        target_dir.mkdir(parents=True, exist_ok=True)
        ctx = WriteContext(
            allowed_builtin=allowed_builtin,
            mcp_server_name=self.mcp_server_name,
            mcp_command=self.mcp_command,
            mcp_url=self.mcp_url,
            mcp_transport=self.mcp_transport,
            servers=self.servers,
            claude_mcp_prefix=self.discovery.claude_mcp_prefix,
        )
        paths: dict[str, Path] = {}
        for writer in self.writers:
            result = writer.write(target_dir, agents, ctx)
            paths[result.key] = result.path
            if verbose and result.summary:
                print(result.summary)
        return paths

    def _mirror_claude_settings(
        self, workspace_path: Path, claude_settings_path: Path
    ) -> None:
        """Mirror the generated Claude settings into ``<workspace>/.claude/settings.json``.

        The mirror preserves any non-``permissions`` keys an operator may
        have set in the workspace's checked-in settings file.
        """
        mirror_dir = workspace_path / ".claude"
        mirror_dir.mkdir(parents=True, exist_ok=True)
        mirror_path = mirror_dir / "settings.json"
        existing: dict = {}
        if mirror_path.is_file():
            try:
                existing = json.loads(mirror_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing = {}
        generated = json.loads(claude_settings_path.read_text(encoding="utf-8"))
        existing["permissions"] = generated["permissions"]
        existing.setdefault("theme", "dark")
        mirror_path.write_text(
            json.dumps(existing, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def get_generated_paths(self, workspace_path: Path) -> dict[str, Path]:
        """Return expected paths without generating."""
        generated_dir = workspace_path / ".agentbox" / "generated"
        return {
            "claude_agents": generated_dir / "claude_agents.json",
            "claude_settings": generated_dir / "claude_settings.json",
            "claude_mcp": generated_dir / "claude_mcp.json",
            "opencode": generated_dir / "opencode.json",
        }


# ---------------------------------------------------------------------------
# Factory — build a ConfigGenerator from project settings + runtime state
# ---------------------------------------------------------------------------


def _try_get_mcp_manifest(mcp_registry: Any) -> Any:
    if mcp_registry is None:
        return None
    try:
        return mcp_registry.manifest
    except Exception:
        return None


def make_generator(
    settings: Settings,
    store: Any,
    mcp_registry: Any,
) -> ConfigGenerator:
    """Build a :class:`ConfigGenerator` for the current project.

    Reads the MCP manifest from the runtime registry and the tool-manifest
    path from the store to build a complete generator config.

    ``mcp_registry`` is typed as ``Any`` to avoid a circular dependency between
    the engines and workspaces domains.  At runtime it is a ``McpRegistry | None``.
    """
    project_root = settings.project_root
    agentbox_toml = project_root / "agentbox.toml"
    mcp_manifest = _try_get_mcp_manifest(mcp_registry)
    servers = store.get_project_mcp_servers()
    mcp_spec = servers[0] if servers else None
    mcp_server_name = mcp_spec.name if mcp_spec else "mcp"
    mcp_url = mcp_spec.url if mcp_spec else None
    mcp_transport = str(mcp_spec.transport) if mcp_spec else "http"
    mcp_command = (
        mcp_spec.command if mcp_spec and mcp_spec.command else ["mcp_serve.sh"]
    )
    static_manifest_path: Path | None = None
    tool_manifest_path = store.get_tool_manifest_path()
    if tool_manifest_path:
        candidate = project_root / tool_manifest_path
        if candidate.exists():
            static_manifest_path = candidate
    return ConfigGenerator(
        agentbox_toml=agentbox_toml,
        manifest_path=static_manifest_path,
        mcp_manifest=mcp_manifest,
        mcp_server_name=mcp_server_name,
        mcp_url=mcp_url,
        mcp_transport=mcp_transport,
        mcp_command=mcp_command,
        verbose=False,
    )
