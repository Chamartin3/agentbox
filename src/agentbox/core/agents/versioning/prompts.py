"""Versioned prompt support for agents.

The DB is the single source of truth: ``agent_versions.prompt_content``
is primary, ``prompt_versions`` committed entries are secondary.
``read_draft`` / ``save_draft`` / ``publish`` / ``rollback`` manage the
draft→committed lifecycle used by the API and executor.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

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
    """Always empty — kept for API wire compatibility."""

    content: str
    size: int
    mtime: str
    """ISO-8601 UTC timestamp."""


# ---------------------------------------------------------------------------
# Versioned layer
# ---------------------------------------------------------------------------


def read_versioned(
    agent_id: str,
    agent_versions: AgentVersionManager,
    prompt_versions: PromptVersionManager,
) -> PromptDoc:
    """Return the active prompt for this agent.

    Priority:
    1. ``agent_versions.prompt_content`` from the active/latest row
       (DB-as-source-of-truth).
    2. ``prompt_versions`` latest committed entry.
    """
    row = agent_versions.get_effective_active(agent_id)
    if row and row.get("prompt_content"):
        content: str = row["prompt_content"] or ""
        return PromptDoc(
            path="",
            content=content,
            size=len(content.encode("utf-8")),
            mtime=row.get("created_at", ""),
        )
    committed = prompt_versions.get_latest_committed(agent_id)
    if committed:
        return PromptDoc(
            path="",
            content=committed["content"],
            size=len(committed["content"].encode("utf-8")),
            mtime=committed["created_at"],
        )
    return PromptDoc(path="", content="", size=0, mtime="")


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
    changelog: str = "",
    author: str = "system",
) -> PromptDoc:
    """Publish the current draft as a new committed version."""
    draft = prompt_versions.get_draft(agent_id)
    if not draft:
        raise PromptError("no_draft", f"no draft for agent {agent_id!r}")
    prompt_versions.patch(draft["id"], is_draft=0, changelog=changelog, created_at=now_iso())
    committed = prompt_versions.get_by_number(agent_id, draft["version"])
    assert committed is not None, f"prompt version {draft['version']} missing after publish"
    return PromptDoc(
        path="",
        content=committed["content"],
        size=len(committed["content"].encode("utf-8")),
        mtime=committed["created_at"],
    )


def rollback(
    agent_id: str,
    prompt_versions: PromptVersionManager,
    target_version: int,
    author: str = "system",
) -> PromptDoc:
    """Rollback to a previous committed version."""
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
    return PromptDoc(
        path="",
        content=committed["content"],
        size=len(committed["content"].encode("utf-8")),
        mtime=committed["created_at"],
    )
