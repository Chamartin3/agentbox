"""Service layer for versioned system-prompt management.

Wraps the low-level ``core.prompt.prompts`` helpers (file I/O + DB
versioning) into a single use-case surface consumed by the REST routes
and the MCP tools. Routes are responsible for mapping the domain
exceptions raised here onto HTTP responses; the service itself raises
plain ``AgentNotFound`` / ``PromptError`` / ``ValueError`` so it stays
transport-agnostic.

Agent resolution follows the project rule that the DB is the single
source of truth: every entry point goes through
``agent_defs.get(agent_id)``.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from agentbox.core.agents.composition import prompts as _prompts
from agentbox.core.agents.composition.prompts import PromptDoc, PromptError
from agentbox.core.data import AgentDef
from agentbox.core.data._util import now_iso
from agentbox.core.data.payload_types import PromptVersionDetail, PromptVersionListResult, PromptVersionSummary
from agentbox.core.db import AgentDefManager, AgentVersionManager, PromptVersionManager

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
    agent_defs: AgentDefManager,
) -> AgentDef:
    """DB-first resolution. Raises ``AgentNotFound`` when missing."""
    agent = agent_defs.get(agent_id)
    if agent is None:
        raise AgentNotFound(agent_id)
    return agent


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def get_prompt(
    agent_id: str,
    *,
    agent_defs: AgentDefManager,
    agent_versions: AgentVersionManager,
    prompt_versions: PromptVersionManager,
    project_root: Path,
) -> PromptDoc:
    """Return the active prompt document for an agent."""
    agent = _resolve_or_raise(agent_id, agent_defs=agent_defs)
    return _prompts.read_versioned(agent, project_root, agent_versions, prompt_versions)


def list_versions(
    agent_id: str,
    *,
    agent_defs: AgentDefManager,
    prompt_versions: PromptVersionManager,
) -> PromptVersionListResult:
    """Return the version-list payload for the prompt-versions endpoint."""
    _resolve_or_raise(agent_id, agent_defs=agent_defs)
    versions = prompt_versions.list_for_agent(agent_id)
    committed = [v for v in versions if not v["is_draft"]]
    drafts = [v for v in versions if v["is_draft"]]
    version_summaries: list[PromptVersionSummary] = [
        PromptVersionSummary(
            version=v["version"],
            is_draft=bool(v["is_draft"]),
            created_at=v["created_at"],
            author=v["author"],
            changelog=v["changelog"],
            size=len(v["content"].encode("utf-8")),
        )
        for v in versions
    ]
    return PromptVersionListResult(
        agent_id=agent_id,
        active_version=committed[0]["version"] if committed else None,
        draft_version=drafts[0]["version"] if drafts else None,
        versions=version_summaries,
    )


def get_version(
    agent_id: str,
    version: int,
    *,
    agent_defs: AgentDefManager,
    prompt_versions: PromptVersionManager,
) -> PromptVersionDetail | None:
    """Return a single prompt version payload, or ``None`` if missing."""
    _resolve_or_raise(agent_id, agent_defs=agent_defs)
    v = prompt_versions.get_by_number(agent_id, version)
    if v is None:
        return None
    return PromptVersionDetail(
        version=v["version"],
        is_draft=bool(v["is_draft"]),
        created_at=v["created_at"],
        author=v["author"],
        changelog=v["changelog"],
        content=v["content"],
        size=len(v["content"].encode("utf-8")),
    )


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


def put_prompt(
    agent_id: str,
    content: str,
    *,
    agent_defs: AgentDefManager,
    prompt_versions: PromptVersionManager,
    project_root: Path,
    author: str = "api",
) -> PromptDoc:
    """Write prompt to disk and capture a new version when changed."""
    agent = _resolve_or_raise(agent_id, agent_defs=agent_defs)
    doc = _prompts.write(agent, project_root, content)
    # Replicate sync_prompt_from_disk: no-op if content matches latest committed.
    new_hash = hashlib.sha256(content.encode()).hexdigest()
    latest = prompt_versions.get_latest_committed(agent_id)
    if latest is not None:
        existing_hash = latest.get("content_hash") or hashlib.sha256(
            latest["content"].encode()
        ).hexdigest()
        if existing_hash != new_hash:
            prompt_versions.insert_committed(
                agent_id,
                content=content,
                content_hash=new_hash,
                author=author,
                changelog="Out-of-band file edit",
                created_at=now_iso(),
                delete_drafts=False,
            )
    else:
        prompt_versions.insert_committed(
            agent_id,
            content=content,
            content_hash=new_hash,
            author=author,
            changelog="Imported from disk",
            created_at=now_iso(),
            delete_drafts=False,
        )
    return doc


def save_draft(
    agent_id: str,
    content: str,
    *,
    agent_defs: AgentDefManager,
    prompt_versions: PromptVersionManager,
    author: str = "system",
) -> PromptDoc:
    """Save a draft prompt version for an agent."""
    _resolve_or_raise(agent_id, agent_defs=agent_defs)
    return _prompts.save_draft(agent_id, prompt_versions, content, author=author)


def publish(
    agent_id: str,
    *,
    agent_defs: AgentDefManager,
    prompt_versions: PromptVersionManager,
    project_root: Path,
    changelog: str = "",
    author: str = "system",
) -> PromptDoc:
    """Publish the current draft and sync the committed body to disk."""
    agent = _resolve_or_raise(agent_id, agent_defs=agent_defs)
    return _prompts.publish(
        agent_id,
        prompt_versions,
        project_root,
        agent=agent,
        changelog=changelog,
        author=author,
    )


def rollback(
    agent_id: str,
    target_version: int,
    *,
    agent_defs: AgentDefManager,
    prompt_versions: PromptVersionManager,
    project_root: Path,
    author: str = "system",
) -> PromptDoc:
    """Roll back to a previous committed version and sync to disk."""
    agent = _resolve_or_raise(agent_id, agent_defs=agent_defs)
    return _prompts.rollback(
        agent_id,
        prompt_versions,
        project_root,
        target_version=target_version,
        agent=agent,
        author=author,
    )
