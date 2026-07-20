"""Serialize/parse an ``AgentDef`` to/from native agent-file formats.

``claude_code`` and ``opencode`` agent files are just YAML frontmatter + a
prompt body, so they are (de)serialized directly here rather than routed
through the per-workspace recipe pipeline (``core/workspaces/build``), which
needs a full ``WorkspaceConfig`` (main agent, mcp, permissions) to render one
file.

ponytail: single .md read/write, no recipe pipeline. Switch to that pipeline
only if export ever needs full workspace fidelity (mcp wiring, permissions).
"""
from __future__ import annotations

import tomlkit
import yaml
from agentbox.core.data import AgentDef
from enum import Enum


class AgentFileFormat(str, Enum):
    """On-disk agent file formats for export/import."""

    claude_code = "claude_code"
    opencode = "opencode"
    codex = "codex"


FORMATS = tuple(f.value for f in AgentFileFormat)


def _frontmatter_doc(meta: dict, body: str) -> str:
    fm = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{fm}\n---\n\n{body.rstrip()}\n"


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Split ``---\\nYAML\\n---\\nbody`` into (meta, body). No frontmatter → ({}, text)."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta = yaml.safe_load(parts[1]) or {}
    if not isinstance(meta, dict):
        meta = {}
    return meta, parts[2].strip()


def dump_agent(agent: AgentDef, fmt: AgentFileFormat) -> list[tuple[str, str]]:
    """Render ``agent`` as ``[(filename, content), ...]`` in ``fmt``."""
    fmt = AgentFileFormat(fmt)  # coerce str → enum (raises ValueError if unknown)
    if fmt is AgentFileFormat.claude_code:
        meta = {"name": agent.id, "description": agent.description or ""}
        return [(f"{agent.id}.md", _frontmatter_doc(meta, agent.prompt or ""))]
    if fmt is AgentFileFormat.opencode:
        meta: dict = {"description": agent.description or ""}
        if agent.tools:
            meta["tools"] = {t: True for t in agent.tools}
        return [(f"{agent.id}.md", _frontmatter_doc(meta, agent.prompt or ""))]
    return _dump_codex(agent)


def _dump_codex(agent: AgentDef) -> list[tuple[str, str]]:
    """Codex subagent TOML: name / description / developer_instructions.

    Mirrors the ``.codex/agents/{id}.toml`` shape the codex backend renders
    at runtime (see engines/backends/codex/render.py). Codex's format carries
    no tool list, so tools are dropped.
    """
    doc = tomlkit.document()
    doc["name"] = agent.id
    doc["description"] = agent.description or ""
    doc["developer_instructions"] = agent.prompt or ""
    return [(f"{agent.id}.toml", tomlkit.dumps(doc))]


def parse_agent(
    text: str, fmt: AgentFileFormat, *, agent_id: str | None = None
) -> AgentDef:
    """Parse an agent file body into an ``AgentDef``.

    ``agent_id`` seeds the id when the format carries none (opencode, or a
    claude_code file without a ``name``) — pass the filename stem.
    """
    fmt = AgentFileFormat(fmt)  # coerce str → enum (raises ValueError if unknown)
    if fmt is AgentFileFormat.claude_code:
        meta, body = _split_frontmatter(text)
        aid = meta.get("name") or agent_id
        if not aid:
            raise ValueError("claude_code agent file has no 'name' and no id hint")
        return AgentDef(id=aid, description=meta.get("description", ""), prompt=body or None)
    if fmt is AgentFileFormat.opencode:
        meta, body = _split_frontmatter(text)
        aid = agent_id or meta.get("name")
        if not aid:
            raise ValueError("opencode agent file needs an id hint (filename stem)")
        raw_tools = meta.get("tools")
        tools = [k for k, v in raw_tools.items() if v] if isinstance(raw_tools, dict) else []
        return AgentDef(
            id=aid, description=meta.get("description", ""), prompt=body or None, tools=tools
        )
    data = tomlkit.parse(text)
    aid = data.get("name") or agent_id
    if not aid:
        raise ValueError("codex agent file has no 'name' and no id hint")
    instructions = data.get("developer_instructions")
    return AgentDef(
        id=str(aid),
        description=str(data.get("description", "")),
        prompt=str(instructions) if instructions else None,
    )
