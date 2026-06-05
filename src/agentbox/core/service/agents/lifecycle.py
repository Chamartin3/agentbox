from __future__ import annotations

from typing import Any

from agentbox.core.data import AgentDef, RunnerProfile, SessionStore


def soft_delete_agent(store: SessionStore, agent_id: str) -> dict | None:
    """Soft-delete an agent. Returns None if not found."""
    return store.soft_delete_agent(agent_id)


def branch_draft(store: SessionStore, agent_id: str, *, author: str) -> dict:
    """Create a new draft version by cloning the active version."""
    return store.branch_draft(agent_id, author=author)


def publish_version(store: SessionStore, agent_id: str, version: int, reason: str) -> dict:
    """Publish a draft version (set as active)."""
    return store.publish_version(agent_id, version, reason)


def rollback_to(
    store: SessionStore, agent_id: str, target_version: int, reason: str, *, author: str
) -> dict:
    """Roll back to a previous agent version (creates a new version)."""
    return store.rollback_to(agent_id, target_version, reason, author=author)


def get_agent_runner_profile(store: SessionStore, agent_id: str) -> RunnerProfile | None:
    """Get the runner profile bound to an agent."""
    return store.get_agent_runner_profile(agent_id)


def set_agent_runner_profile(store: SessionStore, agent_id: str, profile_id: str) -> RunnerProfile:
    """Bind a runner profile to an agent."""
    return store.set_agent_runner_profile(agent_id, profile_id)


def clear_agent_runner_profile(store: SessionStore, agent_id: str) -> None:
    """Remove the runner profile binding from an agent."""
    store.clear_agent_runner_profile(agent_id)


def get_agent_def(store: SessionStore, agent_id: str) -> AgentDef | None:
    """Get the resolved agent definition."""
    return store.get_agent_def(agent_id)


def latest_version(store: SessionStore, agent_id: str) -> dict | None:
    """Get latest version row for an agent."""
    return store.latest_version(agent_id)


def create_agent(
    store: SessionStore,
    agent_id: str,
    config_json: dict,
    *,
    prompt_content: str | None = None,
    author: str,
    changelog: str,
    source: str = "cli",
    source_path: str | None = None,
    source_format: str | None = None,
    sync_mode: str = "off",
    export_to_disk: bool = False,
) -> dict:
    """Create a new agent record."""
    return store.create_agent(
        agent_id=agent_id,
        config_json=config_json,
        prompt_content=prompt_content,
        author=author,
        changelog=changelog,
        source=source,
        source_path=source_path,
        source_format=source_format,
        sync_mode=sync_mode,
        export_to_disk=export_to_disk,
    )


def create_version(
    store: SessionStore,
    agent_id: str,
    source_path: str,
    source_format: str,
    content_snapshot: str,
    prompt_snapshot: str,
    content_hash: str,
    author: str = "system",
    changelog: str = "",
    files: list[dict] | None = None,
    config_json: str | None = None,
    prompt_content: str | None = None,
    source: str = "cli",
) -> dict:
    """Create a new agent version record."""
    return store.create_version(
        agent_id=agent_id,
        source_path=source_path,
        source_format=source_format,
        content_snapshot=content_snapshot,
        prompt_snapshot=prompt_snapshot,
        content_hash=content_hash,
        author=author,
        changelog=changelog,
        files=files,
        config_json=config_json,
        prompt_content=prompt_content,
        source=source,
    )


def get_prompt_version(store: SessionStore, agent_id: str, version: int) -> dict | None:
    """Get a specific prompt version."""
    return store.get_prompt_version(agent_id, version)


def list_agent_tool_grants(
    store: SessionStore, agent_id: str, *, include_revoked: bool = False
) -> list[dict]:
    """List tool grants for an agent."""
    return store.list_agent_tool_grants(agent_id, include_revoked=include_revoked)


def grant_agent_tool(
    store: SessionStore, agent_id: str, tool_name: str, changelog: str, *, actor: str | None = None
) -> dict:
    """Grant tool access to an agent."""
    return store.grant_agent_tool(agent_id, tool_name, changelog, actor=actor)


def revoke_agent_tool(
    store: SessionStore, agent_id: str, tool_name: str, changelog: str, *, actor: str | None = None
) -> None:
    """Revoke tool access from an agent."""
    store.revoke_agent_tool(agent_id, tool_name, changelog, actor=actor)


def list_versions(store: SessionStore, agent_id: str) -> list[dict]:
    """List all versions for an agent."""
    return store.list_versions(agent_id)


def get_active_version(store: SessionStore, agent_id: str) -> dict | None:
    """Get the currently active version for an agent."""
    return store.get_active_version(agent_id)


def get_version(store: SessionStore, agent_id: str, version: int) -> dict | None:
    """Get a specific version by number."""
    return store.get_version(agent_id, version)


def get_rating(store: SessionStore, version_id: int) -> dict | None:
    """Get the rating row for a version."""
    return store.get_rating(version_id)


def list_comments(store: SessionStore, version_id: int) -> list[dict]:
    """List comments for a version."""
    return store.list_comments(version_id)


def add_comment(store: SessionStore, version_id: int, author: str, body: str) -> dict:
    """Add a comment to a version."""
    return store.add_comment(version_id, author, body)


def set_rating(store: SessionStore, version_id: int, rating: int, rater: str) -> dict:
    """Set the rating for a version."""
    return store.set_rating(version_id, rating, rater)


def diff_versions(store: SessionStore, agent_id: str, a: int, b: int) -> dict[str, Any]:
    """Diff two agent versions."""
    return store.diff_versions(agent_id, a, b)


def save_prompt_revision(
    store: SessionStore,
    agent_id: str,
    *,
    prompt_content: str,
    author: str = "cli",
    changelog: str = "",
    activate: bool = False,
) -> dict:
    """Save a prompt revision for an agent (creates a new version)."""
    return store.save_prompt_revision(
        agent_id=agent_id,
        prompt_content=prompt_content,
        author=author,
        changelog=changelog,
        activate=activate,
    )
