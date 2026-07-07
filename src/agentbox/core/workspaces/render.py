"""WorkspaceRenderer — projects a ``WorkspaceBlueprint`` onto disk.

The renderer is the ONLY workspace component that touches the filesystem.
It consumes an immutable blueprint (produced by ``WorkspaceComposer``) and
writes the identical set of artifacts into any target directory — the
persistent workspace workdir OR a fresh per-run run dir (decision 2: the
rendered configuration is identical for every target; the two differ only
in hygiene — a run dir is fresh, a persistent dir gets orphan-reconcile +
provenance).

Every step is best-effort: a failure is logged and appended to
``BuildResult.errors`` but never blocks the following step.
"""

from __future__ import annotations

import json
import logging
import shutil
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from agentbox.core.config import Settings
from agentbox.core.data.constants import MCP_FILENAME
from agentbox.core.data.payload_types import EnvDocRenderEntry, RunSnapshotEntry
from agentbox.core.data.snapshots import workspace_outcomes_to_snapshot
from agentbox.core.data.workenv import Recipe, ResolvedBinding, WorkspaceBlueprint
from agentbox.core.workspaces._types import WorkspaceSyncMeta
from agentbox.core.workspaces.factory import native_extra_items
from agentbox.core.workspaces.generation import WorkspaceConstructor
from agentbox.core.workspaces.generation.workspace_files import (
    materialize_workspace_files,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BuildResult:
    """Outcome of rendering a workspace blueprint into a target dir."""

    workspace_id: str
    target_dir: Path
    snapshot_entries: list[RunSnapshotEntry] = field(default_factory=list)
    env_doc_files: list[str] = field(default_factory=list)
    subagents_written: list[str] = field(default_factory=list)
    bindings_materialized: int = 0
    bindings_skipped: int = 0
    materialized_paths: list[str] = field(default_factory=list)
    orphans_removed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _binding_to_dict(b: ResolvedBinding, *, persistent: bool) -> dict:
    """Project a ``ResolvedBinding`` into the dict shape ``materialize`` reads.

    ponytail: the materializer (``generation/materialize.py``) still consumes
    ``Iterable[dict]``; deep-typing it to accept ``ResolvedBinding`` is deferred
    (see UNIFIED_RESTRUCT_PLAN — typing changes deferred). Retype the
    materializer to drop this bridge.

    For a persistent workspace the per-binding ``on_conflict`` (designed for
    one-shot run dirs) is forced to ``overwrite`` so re-syncs stay current —
    mirrors ``build.py``'s old override.
    """
    on_conflict = b.on_conflict
    if persistent and on_conflict != "skip":
        on_conflict = "overwrite"
    return {
        "binding_id": b.binding_id,
        "resource_id": b.resource_id,
        "version_id": b.version_id,
        "content_hash": b.content_hash,
        "type": b.type,
        "slug": b.slug,
        "display_name": b.display_name,
        "target_path": b.target_path,
        "materialize_mode": b.materialize_mode,
        "on_conflict": on_conflict,
        "blobs": list(b.blobs),
        "skill_meta": b.skill_meta,
        "source_metadata": dict(b.source_metadata) if b.source_metadata else {},
    }


def write_env_doc_files(
    target_dir: Path,
    body: str,
    recipes: Iterable[Recipe],
    *,
    workspace_id: str,
    env_doc_version_id: str | None,
) -> list[EnvDocRenderEntry]:
    """Write the env-doc body to each engine's context file (CLAUDE.md /
    AGENTS.md) and return one snapshot entry per file. Engine-agnostic: the
    same body goes to every recipe's ``context`` layout filename.
    """
    filenames: set[str] = set()
    for recipe in recipes:
        filename = recipe.resolve_layout("context")
        if filename:
            filenames.add(filename)
    entries: list[EnvDocRenderEntry] = []
    for filename in sorted(filenames):
        (target_dir / filename).write_text(body, encoding="utf-8")
        entries.append(
            {
                "role": "env_doc",
                "file": filename,
                "workspace_id": workspace_id,
                "env_doc_version_id": env_doc_version_id or "",
                "bytes": len(body.encode()),
            }
        )
    return entries


def write_secrets(workdir: Path, secrets: Mapping[str, str]) -> None:
    """Write opaque secrets into ``<workdir>/.agentbox/secrets.env``.

    Pure I/O: the renderer never inspects key names or values. The ``.env``
    format is consumed by CLI backends that source the file at startup.
    """
    if not secrets:
        return
    secrets_dir = workdir / ".agentbox"
    secrets_dir.mkdir(parents=True, exist_ok=True)
    env_path = secrets_dir / "secrets.env"
    tmp_path = env_path.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        for key, value in secrets.items():
            escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            f.write(f'{key}="{escaped}"\n')
    shutil.move(str(tmp_path), str(env_path))


def _read_previous_meta(workdir: Path) -> WorkspaceSyncMeta:
    meta_path = workdir / ".agentbox" / "meta.json"
    if not meta_path.exists():
        empty: WorkspaceSyncMeta = {}
        return empty
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        result: WorkspaceSyncMeta = data
        return result
    except Exception:
        empty = {}
        return empty


def _remove_orphan(workdir: Path, rel_path: str) -> bool:
    """Best-effort remove an on-disk path. Returns True if anything was removed."""
    if not rel_path:
        return False
    target = (workdir / rel_path).resolve()
    if not str(target).startswith(str(workdir.resolve())):
        return False  # path escaped workdir — refuse
    if not target.exists() and not target.is_symlink():
        return False
    try:
        if target.is_symlink() or target.is_file():
            target.unlink()
        else:
            shutil.rmtree(target)
        return True
    except Exception:
        logger.exception("workspace render: failed to remove orphan %s", target)
        return False


class WorkspaceRenderer:
    """Writes a ``WorkspaceBlueprint`` to disk. The only FS-touching component."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def render(
        self,
        blueprint: WorkspaceBlueprint,
        target_dir: Path,
        *,
        persistent: bool,
        system_prompt: str | None = None,
        secrets: Mapping[str, str] | None = None,
    ) -> BuildResult:
        target_dir = Path(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        snapshot_entries: list[RunSnapshotEntry] = []
        env_doc_files: list[str] = []
        materialized_paths: list[str] = []
        orphans_removed: list[str] = []
        errors: list[str] = []
        bindings_materialized = 0
        bindings_skipped = 0

        previous_paths: set[str] = set()
        if persistent:
            previous_meta = _read_previous_meta(target_dir)
            previous_paths = set(previous_meta.get("materialized_paths") or [])

        # The blueprint already selected the engine recipes; build the
        # constructor from them (NOT factory.workspace_constructor(), which reloads all).
        constructor = WorkspaceConstructor(
            list(blueprint.recipes), extra_items=native_extra_items
        )

        # ── 1. Resource bindings ──────────────────────────────────────────
        if blueprint.bindings:
            try:
                binding_dicts = [
                    _binding_to_dict(b, persistent=persistent) for b in blueprint.bindings
                ]
                outcomes = constructor.materialize(
                    target_dir,
                    binding_dicts,
                    cache_root=self._settings.resource_cache_dir,
                )
                for o in outcomes:
                    if o.skipped:
                        bindings_skipped += 1
                    else:
                        bindings_materialized += 1
                    if o.target_path:
                        materialized_paths.append(o.target_path)
                snapshot_entries.extend(workspace_outcomes_to_snapshot(outcomes))
            except Exception as e:
                logger.exception(
                    "workspace render: resource materialization failed for %r",
                    blueprint.workspace_id,
                )
                errors.append(f"resources: {e}")

        # ── 2. Env-doc (CLAUDE.md / AGENTS.md, one per engine context file) ─
        if blueprint.env_doc_body is not None:
            try:
                entries = write_env_doc_files(
                    target_dir,
                    blueprint.env_doc_body,
                    blueprint.recipes,
                    workspace_id=blueprint.workspace_id,
                    env_doc_version_id=blueprint.env_doc_version_id,
                )
                for entry in entries:
                    env_doc_files.append(entry["file"])
                    snapshot_entries.append(entry)
            except Exception as e:
                logger.exception(
                    "workspace render: env doc rendering failed for %r",
                    blueprint.workspace_id,
                )
                errors.append(f"env_doc: {e}")

        # ── 3. Native per-engine config (+ empty .mcp.json + workspace files) ─
        try:
            constructor.generate(target_dir, blueprint.config, system_prompt=system_prompt)
        except Exception as e:
            logger.exception(
                "workspace render: native config generation failed for %r",
                blueprint.workspace_id,
            )
            errors.append(f"config: {e}")

        # Claude runs with `--strict-mcp-config`, which errors if .mcp.json is
        # absent; render only emits it when servers exist.
        # ponytail: guarantee an empty one so a server-less run still launches.
        mcp_json = target_dir / MCP_FILENAME
        if not mcp_json.exists():
            mcp_json.write_text('{\n  "mcpServers": {}\n}\n', encoding="utf-8")

        perm_files = (
            blueprint.permissions.get("files") if blueprint.permissions else None
        )
        if perm_files:
            try:
                materialize_workspace_files(
                    target_dir, perm_files, self._settings.project_root
                )
            except Exception as e:
                logger.exception(
                    "workspace render: workspace-file materialization failed for %r",
                    blueprint.workspace_id,
                )
                errors.append(f"workspace_files: {e}")

        # ── 4. Secrets (dead today; secret_keys is empty) ─────────────────
        if secrets:
            try:
                write_secrets(target_dir, secrets)
            except Exception as e:
                logger.exception(
                    "workspace render: secrets write failed for %r",
                    blueprint.workspace_id,
                )
                errors.append(f"secrets: {e}")

        # ── 5. Orphan reconcile (persistent only) ─────────────────────────
        if persistent:
            current_paths = set(materialized_paths)
            for orphan in sorted(previous_paths - current_paths):
                if _remove_orphan(target_dir, orphan):
                    orphans_removed.append(orphan)

        result = BuildResult(
            workspace_id=blueprint.workspace_id,
            target_dir=target_dir,
            snapshot_entries=snapshot_entries,
            env_doc_files=env_doc_files,
            subagents_written=[sa.alias for sa in blueprint.subagents],
            bindings_materialized=bindings_materialized,
            bindings_skipped=bindings_skipped,
            materialized_paths=materialized_paths,
            orphans_removed=orphans_removed,
            errors=errors,
        )

        # ── 6. Provenance (persistent only) ───────────────────────────────
        if persistent:
            _write_provenance(target_dir, result)

        return result


def _write_provenance(workdir: Path, result: BuildResult) -> None:
    meta_dir = workdir / ".agentbox"
    meta_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "workspace_id": result.workspace_id,
        "synced_at": datetime.now(UTC).isoformat(),
        "env_doc_files": result.env_doc_files,
        "subagents_written": result.subagents_written,
        "bindings_materialized": result.bindings_materialized,
        "bindings_skipped": result.bindings_skipped,
        "materialized_paths": result.materialized_paths,
        "orphans_removed": result.orphans_removed,
        "errors": result.errors,
    }
    (meta_dir / "meta.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
