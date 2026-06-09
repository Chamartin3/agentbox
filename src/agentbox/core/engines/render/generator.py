"""ConfigGenerator — drives per-workspace runner config generation."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from ._common import _materialize_workspace_files
from .discovery import AgentDiscovery, DiscoveredAgent

if TYPE_CHECKING:
    from agentbox.core.workspaces.mcp.client import McpToolManifest

# Writers import the builder functions defined above, so this import
# must come after they exist. (Top-of-file import would race the
# circular path agentbox.core.engines.render.generator → writers → generator.)
from agentbox.core.engines.render.writers import (  # noqa: E402
    DEFAULT_WRITERS,
    ConfigWriter,
    WriteContext,
)


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
