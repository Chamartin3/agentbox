"""Service layer for versioned system-prompt management.

Wraps the low-level ``core.prompt.prompts`` helpers (file I/O + DB
versioning) into a single use-case surface consumed by the REST routes
and the MCP tools. Routes are responsible for mapping the domain
exceptions raised here onto HTTP responses; the service itself raises
plain ``AgentNotFound`` / ``PromptError`` / ``ValueError`` so it stays
transport-agnostic.

Agent resolution follows the project rule that the DB is the single
source of truth: every entry point goes through
``store.get_agent_def(agent_id)``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agentbox.core.agents.composition import prompts as _prompts
from agentbox.core.agents.composition.prompts import PromptDoc, PromptError

if TYPE_CHECKING:
    from pathlib import Path

    from agentbox.core.data import AgentDef
    from agentbox.core.db import SessionStore

__all__ = [
    "AgentNotFound",
    "PromptDoc",
    "PromptError",
    "get_prompt",
    "list_versions",
    "get_version",
    "put_prompt",
    "save_draft",
    "publish",
    "rollback",
]


class AgentNotFound(LookupError):
    """Raised when no ``AgentDef`` can be resolved for ``agent_id``."""

    def __init__(self, agent_id: str) -> None:
        super().__init__(f"unknown agent {agent_id!r}")
        self.agent_id = agent_id


def _resolve_or_raise(
    agent_id: str,
    *,
    store: SessionStore,
) -> AgentDef:
    """DB-first resolution. Raises ``AgentNotFound`` when missing."""
    agent = store.get_agent_def(agent_id)
    if agent is None:
        raise AgentNotFound(agent_id)
    return agent


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def get_prompt(
    agent_id: str,
    *,
    store: SessionStore,
    project_root: Path,
) -> PromptDoc:
    """Return the active prompt document for an agent."""
    agent = _resolve_or_raise(agent_id, store=store)
    return _prompts.read_versioned(agent, project_root, store)


def list_versions(
    agent_id: str,
    *,
    store: SessionStore,
) -> dict:
    """Return the version-list payload for the prompt-versions endpoint."""
    _resolve_or_raise(agent_id, store=store)
    versions = store.list_prompt_versions(agent_id)
    committed = [v for v in versions if not v["is_draft"]]
    drafts = [v for v in versions if v["is_draft"]]
    return {
        "agent_id": agent_id,
        "active_version": committed[0]["version"] if committed else None,
        "draft_version": drafts[0]["version"] if drafts else None,
        "versions": [
            {
                "version": v["version"],
                "is_draft": bool(v["is_draft"]),
                "created_at": v["created_at"],
                "author": v["author"],
                "changelog": v["changelog"],
                "size": len(v["content"].encode("utf-8")),
            }
            for v in versions
        ],
    }


def get_version(
    agent_id: str,
    version: int,
    *,
    store: SessionStore,
) -> dict | None:
    """Return a single prompt version payload, or ``None`` if missing."""
    _resolve_or_raise(agent_id, store=store)
    v = store.get_prompt_version(agent_id, version)
    if v is None:
        return None
    return {
        "version": v["version"],
        "is_draft": bool(v["is_draft"]),
        "created_at": v["created_at"],
        "author": v["author"],
        "changelog": v["changelog"],
        "content": v["content"],
        "size": len(v["content"].encode("utf-8")),
    }


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


def put_prompt(
    agent_id: str,
    content: str,
    *,
    store: SessionStore,
    project_root: Path,
    author: str = "api",
) -> PromptDoc:
    """Write prompt to disk and capture a new version when changed."""
    agent = _resolve_or_raise(agent_id, store=store)
    doc = _prompts.write(agent, project_root, content)
    # Capture every disk write as a versioned entry when content changed.
    # No-op if the content matches the latest committed version.
    store.sync_prompt_from_disk(agent_id, content, author=author)
    return doc


def save_draft(
    agent_id: str,
    content: str,
    *,
    store: SessionStore,
    author: str = "system",
) -> PromptDoc:
    """Save a draft prompt version for an agent."""
    _resolve_or_raise(agent_id, store=store)
    return _prompts.save_draft(agent_id, store, content, author=author)


def publish(
    agent_id: str,
    *,
    store: SessionStore,
    project_root: Path,
    changelog: str = "",
    author: str = "system",
) -> PromptDoc:
    """Publish the current draft and sync the committed body to disk."""
    agent = _resolve_or_raise(agent_id, store=store)
    return _prompts.publish(
        agent_id,
        store,
        project_root,
        agent=agent,
        changelog=changelog,
        author=author,
    )


def rollback(
    agent_id: str,
    target_version: int,
    *,
    store: SessionStore,
    project_root: Path,
    author: str = "system",
) -> PromptDoc:
    """Roll back to a previous committed version and sync to disk."""
    agent = _resolve_or_raise(agent_id, store=store)
    return _prompts.rollback(
        agent_id,
        store,
        project_root,
        target_version=target_version,
        agent=agent,
        author=author,
    )
