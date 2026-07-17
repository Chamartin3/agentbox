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
    agentbox = "agentbox"


FORMATS = tuple(f.value for f in AgentFileFormat)

# Fields dropped from the agentbox TOML dump (render-only / prompt sidecar).
_TOML_DROP = ("prompt", "headless", "claude_agent")


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
    return _dump_agentbox(agent)


def _dump_agentbox(agent: AgentDef) -> list[tuple[str, str]]:
    dump = agent.model_dump(mode="json", exclude_none=True)
    for key in _TOML_DROP:
        dump.pop(key, None)
    doc = tomlkit.document()
    doc.add(tomlkit.comment(f" Exported from agentbox — {agent.id}"))
    for key, value in dump.items():
        doc[key] = value
    out = [(f"{agent.id}.toml", tomlkit.dumps(doc))]
    if agent.prompt:
        out.append((f"{agent.id}.prompt.md", agent.prompt))
    return out


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
    # ponytail: agentbox parses the .toml only; the prompt lives in the
    # <id>.prompt.md sidecar and is not merged. Thread the sidecar in if
    # round-trip prompt fidelity for the portable format is ever needed.
    data = dict(tomlkit.parse(text))
    if agent_id:
        data.setdefault("id", agent_id)
    return AgentDef.model_validate(data)
