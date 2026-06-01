"""Per-backend config writers.

Each writer owns one generated file (claude_agents.json,
claude_settings.json, claude_mcp.json, opencode.json). ``ConfigGenerator``
sequences them through the same ``write(target_dir, agents, ctx)``
contract, so a third backend (e.g. Codex) becomes a new class — no
branching in ``ConfigGenerator`` itself.

The four bundled writers wrap the existing builder functions in
``generator.py`` and produce byte-identical output to the previous
inline code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Final, Protocol

from agentbox.core.run.config.discovery import DiscoveredAgent
from agentbox.core.run.config.generator import (
    _dump_json,
    build_claude_agents,
    build_claude_mcp_config,
    build_claude_settings,
    build_opencode_config,
)


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

    key: ClassVar[str] ="claude_agents"
    filename: ClassVar[str] ="claude_agents.json"

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

    key: ClassVar[str] ="claude_settings"
    filename: ClassVar[str] ="claude_settings.json"

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
        allow_count = len(data["permissions"]["allow"])  # type: ignore[union-attr]
        return WriteResult(
            key=self.key,
            path=path,
            summary=f"  Wrote {allow_count} permissions to {path}",
        )


class ClaudeMcpWriter:
    """Emits ``claude_mcp.json`` (Claude ``--mcp-config`` payload)."""

    key: ClassVar[str] ="claude_mcp"
    filename: ClassVar[str] ="claude_mcp.json"

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

    key: ClassVar[str] ="opencode"
    filename: ClassVar[str] ="opencode.json"

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
        agent_block = data["agent"]  # type: ignore[index]
        enabled = [
            k
            for k, v in agent_block.items()  # type: ignore[union-attr]
            if not v.get("disable")  # type: ignore[union-attr]
        ]
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
