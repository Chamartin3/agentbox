"""Drift detector — compares on-disk agent files to the latest version.

Used at startup (sweep all agents) and at run start (stamp the run with
the version id).
"""

from __future__ import annotations

import hashlib
import json
import logging
import warnings
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentbox.core.data.agent_versions import AgentVersionsMixin
    from agentbox.core.data.manifest import AgentDef
    from agentbox.core.data.prompts import PromptVersionsMixin

logger = logging.getLogger(__name__)


class AgentDriftStatus(StrEnum):
    NEW = "new"
    SAME = "same"
    DRIFTED = "drifted"
    UNKNOWN_SOURCE = "unknown_source"


def _compute_file_hash(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_drift(agent: AgentDef, store: AgentVersionsMixin) -> AgentDriftStatus:
    """Compare current agent file hash to the latest stored version."""
    if agent.source_path is None:
        return AgentDriftStatus.UNKNOWN_SOURCE
    latest = store.latest_version(agent.id)
    if latest is None:
        return AgentDriftStatus.NEW
    file_hash = _compute_file_hash(agent.source_path)
    if file_hash is None:
        return AgentDriftStatus.UNKNOWN_SOURCE
    if file_hash == latest["content_hash"]:
        return AgentDriftStatus.SAME
    return AgentDriftStatus.DRIFTED


def _build_snapshot(agent: AgentDef) -> str:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=UserWarning)
        data = agent.model_dump(mode="python")
    return json.dumps(data, sort_keys=True, default=str)


def _sync_prompt(
    agent: AgentDef,
    store: PromptVersionsMixin,
    project_root: Path | None,
) -> None:
    """Capture the on-disk prompt as a new committed prompt version if it changed.

    Independent of agent-definition drift: editing only ``prompt.md`` should
    still produce a new entry in ``prompt_versions`` so the history viewer
    reflects it.
    """
    try:
        if not getattr(agent, "prompt_path", None) and not getattr(
            agent, "prompt", None
        ):
            return
        root = project_root or (
            agent.source_path.parent if agent.source_path else Path()
        )
        content = agent.load_prompt(root) if hasattr(agent, "load_prompt") else ""
        if not content:
            return
        result = store.sync_prompt_from_disk(agent.id, content, author="filesystem")
        if result is not None:
            logger.info(
                "versioning: captured prompt v%d for agent %r (%s)",
                result["version"],
                agent.id,
                result["changelog"],
            )
    except Exception:
        logger.exception("versioning: prompt sync failed for agent %r", agent.id)


def startup_sweep(
    agents: list[AgentDef],
    store: AgentVersionsMixin,
    project_root: Path | None = None,
) -> None:
    """Check every loaded agent and create versions for NEW / DRIFTED agents.

    Also captures on-disk prompt content as a new ``prompt_versions`` entry
    when it differs from the latest committed version. Prompt sync runs for
    every agent (independent of agent-definition drift status) so that
    out-of-band edits to ``prompt.md`` get versioned even when the agent's
    TOML definition is unchanged.
    """
    for agent in agents:
        try:
            status = check_drift(agent, store)
            if status == AgentDriftStatus.NEW:
                file_hash = _compute_file_hash(agent.source_path) or "unknown"
                store.create_version(
                    agent_id=agent.id,
                    source_path=str(agent.source_path) if agent.source_path else "",
                    source_format=(
                        agent.source_format.value if agent.source_format else "unknown"
                    ),
                    content_snapshot=_build_snapshot(agent),
                    prompt_snapshot=agent.load_prompt(
                        agent.source_path.parent if agent.source_path else Path()
                    )
                    if hasattr(agent, "load_prompt") and agent.source_path
                    else "",
                    content_hash=file_hash,
                    author="filesystem",
                    changelog="initial import",
                )
                logger.info("versioning: created v1 for new agent %r", agent.id)
            elif status == AgentDriftStatus.DRIFTED:
                file_hash = _compute_file_hash(agent.source_path) or "unknown"
                store.create_version(
                    agent_id=agent.id,
                    source_path=str(agent.source_path) if agent.source_path else "",
                    source_format=(
                        agent.source_format.value if agent.source_format else "unknown"
                    ),
                    content_snapshot=_build_snapshot(agent),
                    prompt_snapshot="",
                    content_hash=file_hash,
                    author="filesystem",
                    changelog="out-of-band edit",
                )
                logger.info(
                    "versioning: created new version for drifted agent %r",
                    agent.id,
                )
        except Exception:
            logger.exception("versioning: drift check failed for agent %r", agent.id)

        # Always sync prompt content — prompt edits are independent of
        # agent-definition drift and must be versioned in their own table.
        _sync_prompt(agent, store, project_root)
