"""Read / write the prompt file referenced by AgentDef.prompt_path.

Versioned prompt support:
- The DB stores a history of prompt versions per agent (committed + draft).
- The disk file is the delivery mechanism for runners (Claude Code reads
  prompt_path directly). On publish/rollback the committed version is
  written to disk.
- ``read`` / ``write`` remain low-level file ops for backward compat.
- ``read_versioned`` / ``write_to_disk`` / ``read_draft`` / ``save_draft``
  are the versioned layer used by the API and executor.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from agentbox.core.definitions import AgentDef

if TYPE_CHECKING:
    from agentbox.core.data import SessionStore


@dataclass(frozen=True)
class PromptError(Exception):
    code: str
    detail: str

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code}: {self.detail}"


@dataclass
class PromptDoc:
    path: str
    """Project-relative path."""

    content: str
    size: int
    mtime: str
    """ISO-8601 UTC timestamp."""


def _resolve(agent: AgentDef, project_root: Path) -> Path:
    if not agent.prompt_path:
        raise PromptError("no_prompt", f"agent {agent.id!r} has no prompt_path")
    target = (project_root / agent.prompt_path).resolve()
    root = project_root.resolve()
    if not str(target).startswith(str(root) + os.sep) and target != root:
        raise PromptError("path_escape", "prompt_path escapes project root")
    return target


# ---------------------------------------------------------------------------
# Low-level file ops (backward compat)
# ---------------------------------------------------------------------------


def read(agent: AgentDef, project_root: Path) -> PromptDoc:
    target = _resolve(agent, project_root)
    if not target.exists():
        return PromptDoc(path=agent.prompt_path or "", content="", size=0, mtime="")
    stat = target.stat()
    return PromptDoc(
        path=agent.prompt_path or "",
        content=target.read_text(encoding="utf-8"),
        size=stat.st_size,
        mtime=datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(timespec="seconds"),
    )


def write(agent: AgentDef, project_root: Path, content: str) -> PromptDoc:
    target = _resolve(agent, project_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, target)
    return read(agent, project_root)


# ---------------------------------------------------------------------------
# Versioned layer
# ---------------------------------------------------------------------------


def read_versioned(agent: AgentDef, project_root: Path, store: SessionStore) -> PromptDoc:
    """Return the active prompt for this agent.

    Priority:
    1. Latest committed version from the DB.
    2. Fall back to reading the file from disk (backward compat).
    """
    committed = store.get_latest_committed_prompt(agent.id)
    if committed:
        return PromptDoc(
            path=agent.prompt_path or "",
            content=committed["content"],
            size=len(committed["content"].encode("utf-8")),
            mtime=committed["created_at"],
        )
    return read(agent, project_root)


def write_to_disk(agent: AgentDef, project_root: Path, content: str) -> PromptDoc:
    """Write content to the on-disk prompt file.

    Used by publish/rollback so the runner (Claude Code) sees the new
    prompt via prompt_path.
    """
    return write(agent, project_root, content)


def read_draft(agent_id: str, store: SessionStore) -> PromptDoc | None:
    """Return the current draft for an agent, or None."""
    draft = store.get_prompt_draft(agent_id)
    if not draft:
        return None
    return PromptDoc(
        path="",
        content=draft["content"],
        size=len(draft["content"].encode("utf-8")),
        mtime=draft["created_at"],
    )


def save_draft(
    agent_id: str, store: SessionStore, content: str, author: str = "system"
) -> PromptDoc:
    """Save a draft version for an agent."""
    result = store.save_prompt_draft(agent_id, content, author)
    return PromptDoc(
        path="",
        content=result["content"],
        size=len(result["content"].encode("utf-8")),
        mtime=result["created_at"],
    )


def publish(agent_id: str, store: SessionStore, project_root: Path, agent: AgentDef | None = None, changelog: str = "", author: str = "system") -> PromptDoc:
    """Publish the current draft as a committed version and sync to disk."""
    committed = store.publish_prompt(agent_id, changelog, author)
    if agent and agent.prompt_path:
        write_to_disk(agent, project_root, committed["content"])
    return PromptDoc(
        path=agent.prompt_path if agent else "",
        content=committed["content"],
        size=len(committed["content"].encode("utf-8")),
        mtime=committed["created_at"],
    )


def rollback(
    agent_id: str,
    store: SessionStore,
    project_root: Path,
    target_version: int,
    agent: AgentDef | None = None,
    author: str = "system",
) -> PromptDoc:
    """Rollback to a previous committed version and sync to disk."""
    committed = store.rollback_prompt(agent_id, target_version, author)
    if agent and agent.prompt_path:
        write_to_disk(agent, project_root, committed["content"])
    return PromptDoc(
        path=agent.prompt_path if agent else "",
        content=committed["content"],
        size=len(committed["content"].encode("utf-8")),
        mtime=committed["created_at"],
    )
