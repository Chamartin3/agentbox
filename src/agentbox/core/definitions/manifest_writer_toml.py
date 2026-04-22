"""TOML write helpers for standalone and legacy-dir agent formats.

Extracted from manifest_writer.py to keep that module under 400 lines.
"""

from __future__ import annotations

import os
from pathlib import Path

import tomlkit
from tomlkit.items import Table

from agentbox.core.data.manifest import AgentDef, RunnerSpec


def _build_runner_table(r: RunnerSpec) -> Table:
    """Convert a ``RunnerSpec`` to a tomlkit ``Table`` of non-default fields."""
    rt: Table = tomlkit.table()
    if r.model:
        rt["model"] = r.model
    if r.timeout_seconds != 120:
        rt["timeout_seconds"] = r.timeout_seconds
    if r.mcp_config_path:
        rt["mcp_config_path"] = r.mcp_config_path
    if r.allowed_tools:
        arr = tomlkit.array()
        arr.extend(r.allowed_tools)
        rt["allowed_tools"] = arr
    if r.extra_args:
        arr = tomlkit.array()
        arr.extend(r.extra_args)
        rt["extra_args"] = arr
    if r.agent_module:
        rt["agent_module"] = r.agent_module
    if r.output_schema_path:
        rt["output_schema_path"] = r.output_schema_path
    if r.max_validation_retries:
        rt["max_validation_retries"] = r.max_validation_retries
    return rt


def write_standalone_toml(path: Path, agent: AgentDef) -> None:
    """Write a standalone ``.toml`` file for an agent."""
    doc = tomlkit.document()
    doc["id"] = agent.id
    if agent.description:
        doc["description"] = agent.description
    if agent.workspace:
        doc["workspace"] = agent.workspace
    if agent.tools:
        arr = tomlkit.array()
        arr.extend(agent.tools)
        doc["tools"] = arr
    if agent.tags:
        arr = tomlkit.array()
        arr.extend(agent.tags)
        doc["tags"] = arr
    if agent.session_mode != "headless":
        doc["session_mode"] = agent.session_mode
    if not agent.claude_agent:
        doc["claude_agent"] = False
    if agent.headless:
        doc["headless"] = True
    if agent.webhook_url:
        doc["webhook_url"] = agent.webhook_url
    if agent.unsupported_backends:
        arr = tomlkit.array()
        arr.extend(agent.unsupported_backends)
        doc["unsupported_backends"] = arr
    if agent.prompt:
        doc["prompt"] = agent.prompt
    elif agent.prompt_path:
        doc["prompt_path"] = agent.prompt_path

    rt = _build_runner_table(agent.runner)
    doc["runner"] = rt

    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, tomlkit.dumps(doc))


def write_legacy_dir(agent_dir: Path, agent: AgentDef) -> None:
    """Write the legacy agent.toml + prompts/system.md format."""
    agent_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = agent_dir / "agent.toml"
    doc = tomlkit.document()
    doc["id"] = agent.id
    if agent.description:
        doc["description"] = agent.description
    if agent.workspace:
        doc["workspace"] = agent.workspace
    if agent.tools:
        arr = tomlkit.array()
        arr.extend(agent.tools)
        doc["tools"] = arr
    if agent.tags:
        arr = tomlkit.array()
        arr.extend(agent.tags)
        doc["tags"] = arr
    if agent.session_mode != "headless":
        doc["session_mode"] = agent.session_mode
    if agent.webhook_url:
        doc["webhook_url"] = agent.webhook_url

    doc["prompt_path"] = "prompts/system.md"

    rt = _build_runner_table(agent.runner)
    if rt:
        doc["runner"] = rt

    _atomic_write(manifest_path, tomlkit.dumps(doc))

    if agent.prompt:
        prompts_dir = agent_dir / "prompts"
        prompts_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write(prompts_dir / "system.md", agent.prompt)


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
