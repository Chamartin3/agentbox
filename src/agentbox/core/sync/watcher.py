"""File-system watcher for agent definition files.

Observes ``agents.d/``, ``agents/``, and ``agentbox.toml`` / ``manifest.toml``
for changes and creates draft versions in the DB per the agent's ``sync_mode``.

- ``watch`` (default): change → draft version created immediately.
- ``manual``: change detected but no version created until operator acts.
- ``off``: file changes are ignored.

The watcher runs as a background asyncio task started from ``app.py``.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentbox.core.data import SessionStore
    from agentbox.core.definitions.loader import DefinitionLoader

logger = logging.getLogger(__name__)

_DEBOUNCE_S = 0.5


def _file_hash(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


async def _debounce(seconds: float) -> None:
    await asyncio.sleep(seconds)


async def watch_agents(
    store: SessionStore,
    loader: DefinitionLoader,
    project_root: Path,
) -> None:
    """Long-running coroutine — watches agent dirs and creates draft versions.

    Meant to be started as a background task via ``asyncio.create_task()``.
    Cancelled on application shutdown.
    """
    try:
        from watchfiles import Change, awatch  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("watchfiles not installed — sync watcher disabled")
        return

    from agentbox.core.resources.boot_import import (
        import_one_skill,
        resolve_skill_roots,
    )

    watch_paths: list[Path] = []
    for candidate in (
        project_root / "agents.d",
        project_root / "agents",
        loader.manifest_path,
    ):
        if candidate.exists():
            watch_paths.append(candidate)

    skill_roots = resolve_skill_roots(project_root)
    for sr in skill_roots:
        watch_paths.append(sr)

    if not watch_paths:
        logger.info("watcher: no agent paths to watch, exiting")
        return

    logger.info("watcher: watching %s", [str(p) for p in watch_paths])

    pending: set[Path] = set()
    pending_skills: set[Path] = set()  # skill dirs (parent of SKILL.md)
    debounce_task: asyncio.Task | None = None  # type: ignore[type-arg]

    def _match_skill_root(path: Path) -> Path | None:
        for sr in skill_roots:
            try:
                rel = path.relative_to(sr)
            except ValueError:
                continue
            # path must be <root>/<skill_name>/SKILL.md
            if len(rel.parts) >= 2 and rel.name == "SKILL.md":
                return sr
        return None

    async def _flush() -> None:
        await _debounce(_DEBOUNCE_S)
        paths_to_process = list(pending)
        skill_dirs_to_import = list(pending_skills)
        pending.clear()
        pending_skills.clear()
        if paths_to_process:
            await _process_changes(store, loader, project_root)
        for skill_dir in skill_dirs_to_import:
            sr = next(
                (r for r in skill_roots if skill_dir.is_relative_to(r)),
                None,
            )
            if sr is None:
                continue
            try:
                action, slug = import_one_skill(store, skill_dir, project_root)
                logger.info("watcher: skill %s %s", action, slug)
            except Exception:
                logger.exception(
                    "watcher: failed to import skill at %s", skill_dir
                )

    async for changes in awatch(*watch_paths):
        for change_type, path_str in changes:
            if change_type in (Change.added, Change.modified):
                p = Path(path_str)
                sr = _match_skill_root(p)
                if sr is not None:
                    pending_skills.add(p.parent)
                else:
                    pending.add(p)

        if debounce_task is not None and not debounce_task.done():
            debounce_task.cancel()
        debounce_task = asyncio.create_task(_flush())


def _bundle_files_drifted(
    agent,  # AgentDef
    store,
    project_root: Path,
    shared_roots: dict[str, Path],
) -> bool:
    """Always False — disk bundle drift is no longer tracked.

    Bindings are the source of truth: prompt and reference content live in
    ``agent_prompt_resource_bindings`` (plus the repo resources they point
    to), not in ``agent_version_files``. Edits flow through the UI / MCP /
    API, not by hand-editing files on disk. The watcher still reacts to
    ``agent.toml`` changes (via ``check_drift``) so config edits create a
    draft, but per-file drift detection is intentionally a no-op.
    """
    return False


async def _process_changes(
    store: SessionStore,
    loader: DefinitionLoader,
    project_root: Path,
) -> None:
    """Re-scan all agents and create draft versions for changed files."""
    from agentbox.core.versioning.drift import (
        AgentDriftStatus,
        _build_config_json,
        _build_snapshot,
        _compute_file_hash,
        _load_prompt_safe,
        check_drift,
    )

    try:
        manifest = loader.load()
    except Exception:
        logger.exception("watcher: failed to load manifest after change")
        return

    shared_roots = {
        k: (project_root / v).resolve()
        for k, v in (manifest.shared_assets or {}).items()
    }

    for agent in manifest.agents:
        try:
            meta = store.get_agent_meta(agent.id)
            sync_mode = (meta or {}).get("sync_mode", "watch")
            if sync_mode == "off":
                continue

            status = check_drift(agent, store)
            bundle_changed = False
            if status not in (AgentDriftStatus.NEW, AgentDriftStatus.DRIFTED):
                # agent.toml unchanged — check whether a referenced bundle
                # file (system prompt, reference, output schema) changed.
                bundle_changed = _bundle_files_drifted(
                    agent, store, project_root, shared_roots
                )
                if not bundle_changed:
                    continue

            file_hash = _compute_file_hash(agent.source_path) or "unknown"
            prompt_text = _load_prompt_safe(agent)

            if sync_mode == "watch":
                v = store.create_version(
                    agent_id=agent.id,
                    source_path=str(agent.source_path) if agent.source_path else "",
                    source_format=(
                        agent.source_format.value if agent.source_format else "unknown"
                    ),
                    content_snapshot=_build_snapshot(agent),
                    prompt_snapshot=prompt_text,
                    content_hash=file_hash,
                    author="watcher",
                    changelog=(
                        "auto-sync: bundle file changed"
                        if bundle_changed
                        else "auto-sync: file change detected"
                    ),
                    config_json=_build_config_json(agent),
                    prompt_content=prompt_text,
                    source="manifest",
                    is_draft=True,
                    files=None,
                )
                # For NEW agents, auto-activate the first version.
                if status == AgentDriftStatus.NEW:
                    store.activate_version(agent.id, v["id"])
                    store.init_agent_meta(
                        agent_id=agent.id,
                        sync_mode="watch",
                        export_to_disk=True,
                        source_path=str(agent.source_path) if agent.source_path else None,
                        source_format=(
                            agent.source_format.value if agent.source_format else None
                        ),
                    )

                logger.info(
                    "watcher: created draft v%d for agent %r (%s)",
                    v["version"],
                    agent.id,
                    status,
                )
            elif sync_mode == "manual":
                logger.info(
                    "watcher: drift detected for %r (manual mode — no version created)",
                    agent.id,
                )

        except Exception:
            logger.exception("watcher: error processing agent %r", agent.id)
