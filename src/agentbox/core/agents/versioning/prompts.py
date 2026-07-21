"""Versioned prompt support for agents.

The DB is the single source of truth: ``agent_versions.prompt_content``
is primary, ``prompt_versions`` entries are secondary.
``read_versioned`` / ``save_version`` / ``rollback`` manage the
version lifecycle used by the API and executor.

Model: versions are immutable; the latest version is the current prompt.
A "save" writes a new version only when content changed (content-hash
dedup).  There is no draft/publish two-step.
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
    2. ``prompt_versions`` latest entry.
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
    latest = prompt_versions.get_latest(agent_id)
    if latest:
        return PromptDoc(
            path="",
            content=latest["content"],
            size=len(latest["content"].encode("utf-8")),
            mtime=latest["created_at"],
        )
    return PromptDoc(path="", content="", size=0, mtime="")


def save_version(
    agent_id: str,
    prompt_versions: PromptVersionManager,
    content: str,
    author: str = "system",
    changelog: str = "prompt update",
) -> PromptDoc:
    """Save a new prompt version if content changed (content-hash dedup)."""
    new_hash = hashlib.sha256(content.encode()).hexdigest()
    latest = prompt_versions.get_latest(agent_id)
    if latest is not None:
        existing_hash = latest.get("content_hash") or hashlib.sha256(
            latest["content"].encode()
        ).hexdigest()
        if existing_hash == new_hash:
            # No-op — content unchanged.
            return PromptDoc(
                path="",
                content=latest["content"],
                size=len(latest["content"].encode("utf-8")),
                mtime=latest["created_at"],
            )
    result = prompt_versions.insert_version(
        agent_id,
        content=content,
        content_hash=new_hash,
        author=author,
        changelog=changelog,
        created_at=now_iso(),
    )
    return PromptDoc(
        path="",
        content=result["content"],
        size=len(result["content"].encode("utf-8")),
        mtime=result["created_at"],
    )


def rollback(
    agent_id: str,
    prompt_versions: PromptVersionManager,
    target_version: int,
    author: str = "system",
) -> PromptDoc:
    """Roll back by inserting a new version cloning ``target_version``'s content."""
    target = prompt_versions.get_by_number(agent_id, target_version)
    if not target:
        raise PromptError("not_found", f"version {target_version} not found for agent {agent_id!r}")
    result = prompt_versions.insert_version(
        agent_id,
        content=target["content"],
        content_hash=hashlib.sha256(target["content"].encode()).hexdigest(),
        author=author,
        changelog=f"Rollback to version {target_version}",
        created_at=now_iso(),
    )
    return PromptDoc(
        path="",
        content=result["content"],
        size=len(result["content"].encode("utf-8")),
        mtime=result["created_at"],
    )
