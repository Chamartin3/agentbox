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
from typing import TYPE_CHECKING, Protocol, cast

from agentbox.core.agents.config import build_config_json_payload
from agentbox.core.data import RunnerProfileCreate

if TYPE_CHECKING:
    from agentbox.core.data import AgentVersionsMixin
    from agentbox.core.data import AgentDef
    from agentbox.core.data import RunnerProfilesMixin


class _PromptSyncStore(Protocol):
    def sync_prompt_from_disk(
        self,
        agent_id: str,
        content: str,
        author: str = "filesystem",
        changelog: str | None = None,
    ) -> dict | None: ...

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


def _build_config_json(agent: AgentDef) -> str:
    """Serialize an ``AgentDef`` for the ``agent_versions.config_json`` column.

    Distinct from ``_build_snapshot`` (which targets ``content_snapshot``):
    ``config_json`` is the DB-as-source-of-truth payload consumed by
    ``AgentDef.from_db_row`` at runtime, so it MUST round-trip every
    runner field — defaults included — to prevent silent revert to the
    pydantic default at read time.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=UserWarning)
        data = agent.model_dump(mode="json", exclude_none=False)
    # Merge in structured execution/runtime/python sub-dicts so new versions
    # never need the legacy `runner`-fallback path in `agent_config.py`.
    data.update(build_config_json_payload(agent))
    return json.dumps(data, sort_keys=True, default=str)


def _load_prompt_safe(agent: AgentDef) -> str:
    """Read the agent's prompt text, returning ``""`` on any error."""
    try:
        if getattr(agent, "prompt", None):
            return agent.prompt or ""
        if agent.source_path is None:
            return ""
        root = agent.source_path.parent
        if hasattr(agent, "load_prompt"):
            return agent.load_prompt(root)
        return ""
    except Exception:
        logger.exception("versioning: prompt load failed for agent %r", agent.id)
        return ""


def _sync_prompt(
    agent: AgentDef,
    store: _PromptSyncStore,
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
        try:
            content = agent.load_prompt(root) if hasattr(agent, "load_prompt") else ""
        except FileNotFoundError:
            # DB-only agent (or stale prompt_path after rename) — no disk
            # source to sync from. Authoritative content lives in
            # agent_versions.prompt_content; nothing to do here.
            return
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


def _heal_active_pointer(agent_id: str, store: AgentVersionsMixin) -> None:
    """If versions exist but no active pointer, promote the latest one.

    Reproduces the 'orphaned versions' state: rows in ``agent_versions``,
    nothing in ``active_agent_versions``. The runtime resolver would then
    silently fall back to the disk loader, hiding the active version from
    the UI. Heal by activating the latest version.
    """
    try:
        existing = store.get_active_version(agent_id)
        if existing is not None:
            return
        versions = store.list_versions(agent_id)
        if not versions:
            return
        target = versions[0]
        store.activate_version(agent_id, target["id"])
        logger.info(
            "versioning: healed missing active pointer for %r → v%d",
            agent_id,
            target["version"],
        )
    except Exception:
        logger.exception("versioning: heal failed for %r", agent_id)


def _ingest_runner_profile(
    agent: AgentDef,
    agent_id: str,
    store: RunnerProfilesMixin,
) -> None:
    """Create or reuse a runner profile for an agent with a [runner] block.

    Profile ID scheme: ``f"legacy:{agent_id}"`` for stable, idempotent imports.
    Only creates a profile if the agent has a non-empty runner spec.
    """
    if not agent.runner or not agent.runner.kind:
        return

    try:
        profile_id = f"legacy:{agent_id}"

        # Check if profile already exists
        existing = store.get_runner_profile(profile_id)
        if existing is not None:
            # Update binding if needed
            store.set_agent_runner_profile(agent_id, profile_id)
            logger.debug(
                "versioning: reused runner profile %r for agent %r",
                profile_id,
                agent_id,
            )
            return

        # Create new profile from RunnerSpec
        runner_spec = agent.runner
        profile_create = RunnerProfileCreate(
            id=profile_id,
            name=f"Legacy: {agent_id}",
            description="Imported from legacy agent runner config",
            backend=str(runner_spec.kind),
            model=runner_spec.model,
            extra_args=runner_spec.extra_args or [],
        )

        store.create_runner_profile(profile_create)
        store.set_agent_runner_profile(agent_id, profile_id)
        logger.info(
            "versioning: created runner profile %r for agent %r",
            profile_id,
            agent_id,
        )
    except Exception:
        logger.exception(
            "versioning: failed to ingest runner profile for agent %r", agent_id
        )


def _collect_version_files(agent: AgentDef) -> list[dict] | None:
    """Snapshot bundle files referenced by composition (schemas, etc.)
    into agent_version_files so the composer can resolve them from the
    active version row without re-reading disk."""
    if agent.composition is None or agent.source_path is None:
        return None
    bundle_dir = agent.source_path.parent
    files: list[dict] = []
    for slot in ("output_schema", "input_schema", "user_template"):
        rel = getattr(agent.composition, slot, None)
        if not rel:
            continue
        p = bundle_dir / rel
        if not p.is_file():
            continue
        try:
            content = p.read_text(encoding="utf-8")
        except OSError:
            continue
        files.append(
            {
                "relative_path": rel,
                "kind": slot if slot != "user_template" else "user_template",
                "content": content,
            }
        )
    return files or None


def startup_sweep(
    agents: list[AgentDef],
    store: AgentVersionsMixin,
    project_root: Path | None = None,
    shared_roots: dict[str, Path] | None = None,
) -> None:
    """Check every loaded agent and create versions for NEW / DRIFTED agents.

    Also captures on-disk prompt content as a new ``prompt_versions`` entry
    when it differs from the latest committed version. Prompt sync runs for
    every agent (independent of agent-definition drift status) so that
    out-of-band edits to ``prompt.md`` get versioned even when the agent's
    TOML definition is unchanged.

    For agents with a [runner] block, creates or reuses a runner profile
    and binds it to the agent (Phase 13f import).
    """
    shared_roots = shared_roots or {}
    for agent in agents:
        try:
            status = check_drift(agent, store)
            _heal_active_pointer(agent.id, store)
            if status == AgentDriftStatus.NEW:
                file_hash = _compute_file_hash(agent.source_path) or "unknown"
                prompt_text = (
                    agent.load_prompt(
                        agent.source_path.parent if agent.source_path else Path()
                    )
                    if hasattr(agent, "load_prompt") and agent.source_path
                    else ""
                )
                store.create_version(
                    agent_id=agent.id,
                    source_path=str(agent.source_path) if agent.source_path else "",
                    source_format=(
                        agent.source_format.value if agent.source_format else "unknown"
                    ),
                    content_snapshot=_build_snapshot(agent),
                    prompt_snapshot=prompt_text,
                    content_hash=file_hash,
                    author="filesystem",
                    changelog="initial import",
                    prompt_content=prompt_text or None,
                    config_json=_build_config_json(agent),
                    files=_collect_version_files(agent),
                )
                logger.info("versioning: created v1 for new agent %r", agent.id)
                # Import runner profile if agent has [runner] block
                if hasattr(store, "create_runner_profile"):
                    _ingest_runner_profile(agent, agent.id, store)  # type: ignore
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
                    files=None,
                )
                logger.info(
                    "versioning: created new version for drifted agent %r",
                    agent.id,
                )
        except Exception:
            logger.exception("versioning: drift check failed for agent %r", agent.id)

        # Always sync prompt content — prompt edits are independent of
        # agent-definition drift and must be versioned in their own table.
        _sync_prompt(agent, cast(_PromptSyncStore, store), project_root)

    # Phase 5: degraded-mode boot — warn (don't fail) for agents with no
    # runner profile binding. They remain non-runnable until bound; the
    # executor enforces this at dispatch time via `_fail_pre_run`.
    if hasattr(store, "get_agent_runner_profile"):
        for agent in agents:
            try:
                binding = store.get_agent_runner_profile(agent.id)  # type: ignore[attr-defined]
                if binding is None:
                    logger.warning(
                        "versioning: agent %r has no runner profile bound — "
                        "runs will fail until one is assigned via "
                        "/api/agents/%s/runner-profile",
                        agent.id,
                        agent.id,
                    )
            except Exception:
                pass
