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

import hashlib
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from agentbox.core.data import AgentDef
from agentbox.core.data._util import now_iso
from agentbox.core.db import AgentVersionManager, PromptVersionManager


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


def read_versioned(
    agent: AgentDef,
    project_root: Path,
    agent_versions: AgentVersionManager,
    prompt_versions: PromptVersionManager,
) -> PromptDoc:
    """Return the active prompt for this agent.

    Priority:
    1. ``agent_versions.prompt_content`` from the active/latest row
       (DB-as-source-of-truth).
    2. Legacy ``prompt_versions`` committed entry.
    3. Fall back to reading the file from disk (backward compat).
    """
    row = agent_versions.get_active(agent.id) or agent_versions.get_latest(agent.id)
    if row and row.get("prompt_content"):
        content: str = row["prompt_content"] or ""
        return PromptDoc(
            path=agent.prompt_path or "",
            content=content,
            size=len(content.encode("utf-8")),
            mtime=row.get("created_at", ""),
        )
    committed = prompt_versions.get_latest_committed(agent.id)
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


def read_draft(agent_id: str, prompt_versions: PromptVersionManager) -> PromptDoc | None:
    """Return the current draft for an agent, or None."""
    draft = prompt_versions.get_draft(agent_id)
    if not draft:
        return None
    return PromptDoc(
        path="",
        content=draft["content"],
        size=len(draft["content"].encode("utf-8")),
        mtime=draft["created_at"],
    )


def save_draft(
    agent_id: str, prompt_versions: PromptVersionManager, content: str, author: str = "system"
) -> PromptDoc:
    """Save a draft version for an agent."""
    result = prompt_versions.replace_draft(
        agent_id,
        content=content,
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        author=author,
        changelog="",
        created_at=now_iso(),
    )
    return PromptDoc(
        path="",
        content=result["content"],
        size=len(result["content"].encode("utf-8")),
        mtime=result["created_at"],
    )


def publish(
    agent_id: str,
    prompt_versions: PromptVersionManager,
    project_root: Path,
    agent: AgentDef | None = None,
    changelog: str = "",
    author: str = "system",
) -> PromptDoc:
    """Publish the current draft as a committed version and sync to disk."""
    draft = prompt_versions.get_draft(agent_id)
    if not draft:
        raise PromptError("no_draft", f"no draft for agent {agent_id!r}")
    prompt_versions.patch(draft["id"], is_draft=0, changelog=changelog, created_at=now_iso())
    committed = prompt_versions.get_by_number(agent_id, draft["version"])
    assert committed is not None, f"prompt version {draft['version']} missing after publish"
    if agent and agent.prompt_path:
        write_to_disk(agent, project_root, committed["content"])
    return PromptDoc(
        path=agent.prompt_path if agent and agent.prompt_path else "",
        content=committed["content"],
        size=len(committed["content"].encode("utf-8")),
        mtime=committed["created_at"],
    )


def rollback(
    agent_id: str,
    prompt_versions: PromptVersionManager,
    project_root: Path,
    target_version: int,
    agent: AgentDef | None = None,
    author: str = "system",
) -> PromptDoc:
    """Rollback to a previous committed version and sync to disk."""
    target = prompt_versions.get_by_number(agent_id, target_version)
    if not target:
        raise PromptError("not_found", f"version {target_version} not found for agent {agent_id!r}")
    if target["is_draft"]:
        raise PromptError("is_draft", f"cannot rollback to a draft version ({target_version})")
    committed = prompt_versions.insert_committed(
        agent_id,
        content=target["content"],
        content_hash=hashlib.sha256(target["content"].encode()).hexdigest(),
        author=author,
        changelog=f"Rollback to version {target_version}",
        created_at=now_iso(),
        delete_drafts=True,
    )
    if agent and agent.prompt_path:
        write_to_disk(agent, project_root, committed["content"])
    return PromptDoc(
        path=agent.prompt_path if agent and agent.prompt_path else "",
        content=committed["content"],
        size=len(committed["content"].encode("utf-8")),
        mtime=committed["created_at"],
    )
