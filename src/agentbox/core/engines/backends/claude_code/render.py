"""Render helpers and tool resolution for the Claude Code backend."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from agentbox.core.engines.backends.base import (
    BackendConfigGenerator,
    ComposedContext,
    HasAgentConfig,
    McpConfig,
    RuntimeConfigView,
)

if TYPE_CHECKING:
    from agentbox.core.data import AgentDef


def _runtime_config_view_from_agent(agent: HasAgentConfig) -> RuntimeConfigView:
    """Fallback: read ``allowed_tools`` from the agent's ``_config_json``.

    Needed only when the executor does NOT supply ``runtime_config``
    explicitly (e.g. direct ``render()`` calls in tests).
    """
    raw = getattr(agent, "_config_json", None)
    if raw is None:
        return RuntimeConfigView()
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return RuntimeConfigView()
    runtime_section = (raw or {}).get("runtime") if isinstance(raw, dict) else None
    if not isinstance(runtime_section, dict):
        return RuntimeConfigView()
    return RuntimeConfigView(
        allowed_tools=tuple(runtime_section.get("allowed_tools") or ()),
    )


def _intersect_allowed_tools(
    agent_tools: list[str], workspace_tools: list[str] | None
) -> list[str]:
    """Effective allow list = agent ∩ workspace.

    If either side is empty/None, treat it as "no restriction" so the
    other side governs alone.
    """
    if not agent_tools and not workspace_tools:
        return []
    if not agent_tools:
        return list(workspace_tools or [])
    if not workspace_tools:
        return list(agent_tools)
    ws_set = set(workspace_tools)
    return [t for t in agent_tools if t in ws_set]


__all__ = [
    "ClaudeCodeConfigGenerator",
    "_intersect_allowed_tools",
    "_runtime_config_view_from_agent",
]


class ClaudeCodeConfigGenerator(BackendConfigGenerator):
    def generate(
        self,
        backend_dir: Path,
        agent: AgentDef,
        composed: ComposedContext,
        mcp: McpConfig | None = None,
    ) -> None:
        self._write_agents_json(backend_dir, agent)
        self._write_agent_markdown(backend_dir, agent, composed)
        self._write_settings_json(backend_dir)
        self._write_claude_mcp_json(backend_dir, mcp)
        self._write_claude_md(backend_dir, composed)

    def _write_agents_json(self, backend_dir: Path, agent: AgentDef) -> None:
        """Write legacy agents.json that points at the markdown agent file."""
        agents_json = backend_dir / "agents.json"
        if agents_json.exists():
            return

        data = {
            "agents": [
                {
                    "name": agent.id,
                    "description": agent.description or "",
                    "source": f"agents/{agent.id}.md",
                }
            ]
        }
        agents_json.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _write_agent_markdown(
        self,
        backend_dir: Path,
        agent: AgentDef,
        composed: ComposedContext,
    ) -> None:
        """Generate agents/<agent_id>.md with YAML frontmatter + full prompt."""
        agents_dir = backend_dir / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)

        md_path = agents_dir / f"{agent.id}.md"
        if md_path.exists():
            return

        frontmatter = self._build_frontmatter(agent)
        full_prompt = "\n\n".join(
            p for p in (composed.system, composed.user) if p
        )

        md_path.write_text(f"{frontmatter}\n\n{full_prompt}", encoding="utf-8")

    def _write_settings_json(self, backend_dir: Path) -> None:
        """Write minimal claude_settings.json."""
        settings_json = backend_dir / "settings.json"
        if settings_json.exists():
            return
        data = {
            "allowed_tools": ["Edit", "Read", "Bash"],
            "auto_run": True,
        }
        settings_json.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _write_claude_mcp_json(
        self,
        backend_dir: Path,
        mcp: McpConfig | None,
    ) -> None:
        """Write claude_mcp.json with MCP server configuration."""
        if mcp is None:
            return
        mcp_json = backend_dir / "claude_mcp.json"
        if mcp_json.exists():
            return

        if mcp.url:
            entry: dict[str, object] = {"type": mcp.transport, "url": mcp.url}
        else:
            entry = {
                "command": mcp.command[0] if mcp.command else "mcp_serve.sh",
                "args": list(mcp.command[1:])
                if mcp.command and len(mcp.command) > 1
                else [],
            }
        data = {"mcpServers": {mcp.server_name: entry}}
        mcp_json.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _write_claude_md(self, backend_dir: Path, composed: ComposedContext) -> None:
        """Write CLAUDE.md as fallback (copy of system prompt)."""
        claude_md = backend_dir / "CLAUDE.md"
        if claude_md.exists():
            return
        claude_md.write_text(composed.system, encoding="utf-8")

    def _build_frontmatter(self, agent: AgentDef) -> str:
        lines = ["---"]
        lines.append(f"name: {agent.id}")
        if agent.description:
            lines.append(f'description: "{agent.description}"')
        if agent.runner.model:
            lines.append(f"model: {agent.runner.model}")
        lines.append("tools:")
        lines.append("  - Edit")
        lines.append("  - Read")
        lines.append("  - Bash")
        lines.append("---")
        return "\n".join(lines)
