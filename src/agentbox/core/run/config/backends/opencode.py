"""OpenCode backend config generator.

Produces:
- opencode.json (workspace config with agent list + MCP)
- agents/<agent_id>.md (per-agent markdown with YAML frontmatter)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from agentbox.core.run.config.backends.base import (
    BackendConfigGenerator,
    McpConfig,
)
from agentbox.core.run.config.prompt_composer import PromptComposer

if TYPE_CHECKING:
    from agentbox.core.data.manifest import AgentDef
    from agentbox.core.run.config.run_configurator import ComposedMetadata


class OpenCodeConfigGenerator(BackendConfigGenerator):
    def generate(
        self,
        backend_dir: Path,
        agent: AgentDef,
        composed: ComposedMetadata,
        mcp: McpConfig | None = None,
    ) -> None:
        self._write_opencode_json(backend_dir, agent, mcp)
        self._write_agent_markdown(backend_dir, agent, composed)

    def _write_opencode_json(
        self,
        backend_dir: Path,
        agent: AgentDef,
        mcp: McpConfig | None,
    ) -> None:
        """Write workspace-level opencode.json with agent list + MCP config."""
        oc_json = backend_dir / "opencode.json"
        if oc_json.exists():
            return

        config: dict[str, object] = {
            "$schema": "https://opencode.ai/config.json",
            "theme": "dracula",
            "tools": {"skill": True},
            "permission": {"*": "allow"},
            "agent": {
                agent.id: {
                    "description": agent.description or "",
                }
            },
        }

        if mcp is not None:
            config["mcp"] = {
                mcp.server_name: self._build_mcp_entry(mcp)
            }

        oc_json.write_text(json.dumps(config, indent=2), encoding="utf-8")

    def _build_mcp_entry(self, mcp: McpConfig) -> dict[str, object]:
        """Build OpenCode-specific MCP entry."""
        if mcp.url:
            return {"type": "remote", "url": mcp.url, "enabled": True}
        return {
            "type": "local",
            "command": mcp.command or ["mcp_serve.sh"],
            "enabled": True,
        }

    def _write_agent_markdown(
        self,
        backend_dir: Path,
        agent: AgentDef,
        composed: ComposedMetadata,
    ) -> None:
        """Generate agents/<agent_id>.md with YAML frontmatter + full prompt."""
        agents_dir = backend_dir / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)

        md_path = agents_dir / f"{agent.id}.md"
        if md_path.exists():
            return

        frontmatter = self._build_frontmatter(agent)
        full_prompt = PromptComposer.assemble_full_prompt(composed)

        md_path.write_text(f"{frontmatter}\n\n{full_prompt}", encoding="utf-8")

    def _build_frontmatter(self, agent: AgentDef) -> str:
        lines = ["---"]
        if agent.description:
            lines.append(f'description: "{agent.description}"')
        if agent.runner.model:
            lines.append(f"model: {agent.runner.model}")
        lines.append("tools:")
        lines.append("  skill_list: true")
        lines.append("  skill_get_content: true")
        lines.append("---")
        return "\n".join(lines)
