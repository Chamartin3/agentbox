"""Agent discovery — reads agentbox.toml and loads prompts.

Single source of truth is ``agentbox.toml``. Discovers agents from the
inline ``[[agents]]`` entries and loads their system prompts from disk
or from the inline ``prompt`` field.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import TypedDict

from agentbox.core.mcp import McpToolManifest


class DiscoveredAgent(TypedDict):
    name: str
    description: str
    prompt: str
    mcp_tools: list[str]


def _deduplicate(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


class AgentDiscovery:
    """Reads ``agentbox.toml`` and loads prompts from ``prompt_path`` files.

    Parameters
    ----------
    agentbox_toml:
        Path to the single-source-of-truth manifest (default
        ``<project_root>/agentbox.toml``).
    mcp_manifest:
        The runtime MCP tool manifest (introspected from MCP servers).
        When *None* falls back to the legacy ``manifest_path`` for
        backward compatibility.
    manifest_path:
        Legacy path to tool_manifest.json. Only consulted when
        ``mcp_manifest`` is *None*.
    verbose:
        When *True* (default) prints progress to stdout.
    """

    def __init__(
        self,
        agentbox_toml: Path,
        manifest_path: Path | None = None,
        *,
        mcp_manifest: McpToolManifest | None = None,
        mcp_server_name: str | None = None,
        verbose: bool = True,
    ) -> None:
        self.agentbox_toml = agentbox_toml
        self.project_root = agentbox_toml.parent
        self.manifest_path = manifest_path
        self.verbose = verbose
        self._manifest_data: dict[str, list[str]] | None = None
        self._mcp_manifest = mcp_manifest
        self._mcp_server_name = mcp_server_name
        self.claude_mcp_prefix = (
            f"mcp__{mcp_server_name}__" if mcp_server_name else "mcp__"
        )

    @property
    def manifest(self) -> dict[str, list[str]]:
        if self._mcp_manifest is not None:
            groups = self._mcp_manifest.groups
            if groups:
                result: dict[str, list[str]] = {}
                for key, tool_names in groups.items():
                    _, _, suffix = key.partition(".")
                    dot = suffix.find(".")
                    if dot == -1:
                        result[suffix] = tool_names
                    else:
                        prefix = suffix[:dot]
                        sub = suffix[dot + 1 :]
                        if sub == "read" or sub == "write":
                            group_name = f"{prefix}.{sub}"
                        else:
                            group_name = prefix
                        result[group_name] = result.get(group_name, []) + tool_names
                return result
            # MCP manifest present but empty — fall through to static file.
        if self._manifest_data is None and self.manifest_path is not None:
            with open(self.manifest_path) as f:
                self._manifest_data = json.load(f)
        return self._manifest_data or {}

    def resolve_tools(self, raw_tools: list[str]) -> list[str]:
        result: list[str] = []
        for tool in raw_tools:
            if tool.startswith("@"):
                group_name = tool[1:]
                if group_name not in self.manifest:
                    raise ValueError(f"Unknown tool group: {group_name}")
                for tool_name in self.manifest[group_name]:
                    result.append(f"{self.claude_mcp_prefix}{tool_name}")
            else:
                result.append(tool)
        return _deduplicate(result)

    def discover_mcp_agents(self) -> list[DiscoveredAgent]:
        entries = self._load_agents()

        agents: list[DiscoveredAgent] = []

        for entry in entries:
            if not entry.get("claude_agent", True):
                self._log(f"  Skipped (pydantic-only): {entry.get('id', '?')}")
                continue

            prompt = self._load_prompt(entry)
            if not prompt:
                self._log(f"  WARNING: No prompt for {entry.get('id', '?')}, skipping")
                continue

            name = entry["id"]
            raw_tools = entry.get("tools", [])
            mcp_tools = self.resolve_tools(raw_tools)

            agents.append(
                DiscoveredAgent(
                    name=name,
                    description=entry.get("description", ""),
                    prompt=prompt,
                    mcp_tools=mcp_tools,
                )
            )
            self._log(f"  Loaded: {name} ({len(prompt)} chars, {len(mcp_tools)} tools)")

        return agents

    def _load_agents(self) -> list[dict]:
        if not self.agentbox_toml.exists():
            self._log(f"  WARNING: {self.agentbox_toml} not found")
            return []
        with self.agentbox_toml.open("rb") as f:
            data = tomllib.load(f)
        return data.get("agents", [])

    def _load_prompt(self, entry: dict) -> str:
        inline = entry.get("prompt")
        if inline:
            return str(inline).strip()
        prompt_path = entry.get("prompt_path")
        if prompt_path:
            path = self.project_root / str(prompt_path)
            if path.exists():
                return path.read_text(encoding="utf-8").strip()
        return ""

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg)
