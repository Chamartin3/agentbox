"""Render workspace subagents into per-backend markdown folders.

Each subagent (a composed agent assigned to a workspace) is written as
``{alias}.md`` into the backend-specific agents directory:

- ``.claude/agents/{alias}.md``
- ``.opencode/agents/{alias}.md``
- ``.codex/agents/{alias}.md``

The body is the agent's active prompt content with a small YAML
frontmatter header (name, description). Mirrors how SKILL.md works.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

BACKEND_AGENT_DIRS = (
    ".claude/agents",
    ".opencode/agents",
    ".codex/agents",
)


@dataclass(frozen=True)
class SubagentRenderOutcome:
    workspace_id: str
    agent_id: str
    alias: str
    files_written: list[str]


def _render_markdown(alias: str, description: str | None, prompt: str) -> str:
    desc = (description or "").replace("\n", " ").strip()
    header = "---\n"
    header += f"name: {alias}\n"
    if desc:
        header += f"description: {desc}\n"
    header += "---\n\n"
    body = prompt.rstrip() + "\n"
    return header + body


def materialize_subagents(
    workdir: Path,
    resolved_subagents: Iterable[dict],
    *,
    backend_dirs: tuple[str, ...] = BACKEND_AGENT_DIRS,
) -> list[SubagentRenderOutcome]:
    """Write each subagent into every backend's agents folder.

    Each entry in ``resolved_subagents`` must include:
        workspace_id, agent_id, alias, description, prompt_content.
    """
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    outcomes: list[SubagentRenderOutcome] = []
    for s in resolved_subagents:
        alias = s["alias"]
        body = _render_markdown(
            alias,
            s.get("description"),
            s.get("prompt_content") or "",
        )
        written: list[str] = []
        for rel_dir in backend_dirs:
            dest_dir = workdir / Path(*rel_dir.split("/"))
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / f"{alias}.md"
            dest.write_text(body, encoding="utf-8")
            written.append(str(dest.relative_to(workdir)))
        outcomes.append(
            SubagentRenderOutcome(
                workspace_id=s["workspace_id"],
                agent_id=s["agent_id"],
                alias=alias,
                files_written=written,
            )
        )
    return outcomes
