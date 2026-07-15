"""Workspace WRITE side — ``WorkspaceBuilder`` projects a blueprint onto disk.

The builder is the ONLY workspace component that touches the filesystem. It
consumes an immutable ``WorkspaceBlueprint`` (produced by ``WorkspaceComposer``)
and writes the identical set of artifacts into any target directory — the
persistent workspace workdir OR a fresh per-run run dir (the rendered
configuration is identical for every target; the two differ only in hygiene —
a run dir is fresh, a persistent dir gets orphan-reconcile + provenance).

This package owns the whole write pipeline: ``engine`` (recipe-driven config
files), ``bindings`` (resource blobs), ``files`` (declared host-file copies),
``_paths`` (safe destination resolution). ``WorkspaceConstructor`` +
``workspace_constructor()`` (the recipe fan-out + registry wiring) live here
too — engines never imports workspaces, so no bridge module is needed.

Every step is best-effort: a failure is logged and appended to
``BuildResult.errors`` but never blocks the following step.
"""

from __future__ import annotations

import json
import logging
import shutil
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from agentbox.core.config import Settings
from agentbox.core.data.constants import MCP_FILENAME
from agentbox.core.data.payload_types import (
    BindingDict,
    EnvDocRenderEntry,
    McpStdioServerSpec,
    RunSnapshotEntry,
)
from agentbox.core.data.snapshots import workspace_outcomes_to_snapshot
from agentbox.core.data.workenv import (
    Item,
    RenderedDir,
    Recipe,
    ResolvedBinding,
    WorkspaceBlueprint,
    WorkspaceConfig,
)
from agentbox.core.data.workenv import MaterializeOutcome as MaterializeOutcome
from agentbox.core.engines.backends.recipe_loader import (
    backend_for_engine,
    list_recipes,
    load_recipe,
)
from agentbox.core.workspaces._types import WorkspaceSyncMeta
from agentbox.core.workspaces.build.bindings import materialize_workspace
from agentbox.core.workspaces.build.engine import render

logger = logging.getLogger(__name__)


# ── Recipe fan-out + registry wiring (dissolved from construct.py + factory.py) ─

# (engine, config) -> extra native config items for that engine.
ExtraItemsFn = Callable[[str, WorkspaceConfig], list[Item]]


def native_extra_items(engine: str, config: WorkspaceConfig) -> list[Item]:
    """Per-engine native config items (opencode.json, codex TOML, …)."""
    try:
        return backend_for_engine(engine).build_workspace_items(config)
    except KeyError:
        return []


class WorkspaceConstructor:
    """Generate + materialize a workenv across several engine recipes."""

    def __init__(
        self,
        recipes: Iterable[Recipe],
        *,
        extra_items: ExtraItemsFn | None = None,
    ) -> None:
        self._recipes = list(recipes)
        self._extra_items = extra_items

    @property
    def recipes(self) -> list[Recipe]:
        return list(self._recipes)

    def generate(
        self,
        target_dir: Path,
        config: WorkspaceConfig,
        *,
        system_prompt: str | None = None,
    ) -> list[RenderedDir]:
        """Render *config* to *target_dir* once per recipe. Engine-agnostic."""
        rendered: list[RenderedDir] = []
        for recipe in self._recipes:
            extra = self._extra_items(recipe.engine, config) if self._extra_items else []
            rendered.append(
                render(
                    target_dir,
                    config,
                    recipe,
                    system_prompt=system_prompt,
                    extra_items=extra,
                )
            )
        return rendered

    def materialize(
        self,
        workdir: Path,
        resolved_bindings: Iterable[BindingDict],
        *,
        cache_root: Path | None = None,
    ) -> list[MaterializeOutcome]:
        """Materialize resource bindings; skills land per-recipe layout."""
        return materialize_workspace(
            workdir,
            resolved_bindings,
            recipes=self._recipes,
            cache_root=cache_root,
        )


def workspace_constructor() -> WorkspaceConstructor:
    """A ``WorkspaceConstructor`` wired to every registered engine recipe."""
    return WorkspaceConstructor(
        [load_recipe(e) for e in list_recipes()],
        extra_items=native_extra_items,
    )


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


def _binding_to_dict(b: ResolvedBinding, *, persistent: bool) -> BindingDict:
    """Project a ``ResolvedBinding`` into the dict shape ``materialize`` reads.

    ponytail: the materializer (``build.materialize`` + ``build/bindings.py``)
    consumes the typed ``Iterable[BindingDict]``; this bridge projects the
    ``ResolvedBinding`` dataclass into it. Optional cleanup: thread
    ``ResolvedBinding`` through the materializer directly and drop this bridge —
    discretionary, no type-safety gain (both shapes are already typed).

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
        "source_metadata": b.source_metadata or {},
    }


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


class WorkspaceBuilder:
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
        extra_mcp_servers: Mapping[str, McpStdioServerSpec] | None = None,
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

        # ── 2. Native per-engine config — the SOLE writer of every file,
        # including the instruction/context file (CLAUDE.md / AGENTS.md). The
        # env-doc snapshot entries are derived from what it actually wrote (no
        # parallel raw-body write path). ────────────────────────────────────
        try:
            rendered_dirs = constructor.generate(
                target_dir, blueprint.config, system_prompt=system_prompt
            )
        except Exception as e:
            logger.exception(
                "workspace render: native config generation failed for %r",
                blueprint.workspace_id,
            )
            errors.append(f"config: {e}")
            rendered_dirs = []

        # Env-doc provenance: only when the workspace actually has an env-doc
        # body (parity with the old step-2 guard). When a per-run system_prompt
        # replaced the body, the context file holds the prompt, NOT the env-doc
        # version — so record no version id rather than a false one.
        if blueprint.env_doc_body is not None:
            version_id = (
                blueprint.env_doc_version_id if system_prompt is None else ""
            )
            for rendered_dir in rendered_dirs:
                for item in rendered_dir.items:
                    if item.role != "context" or item.file in env_doc_files:
                        continue
                    env_doc_files.append(item.file)
                    entry: EnvDocRenderEntry = {
                        "role": "env_doc",
                        "file": item.file,
                        "workspace_id": blueprint.workspace_id,
                        "env_doc_version_id": version_id or "",
                        "bytes": item.bytes,
                    }
                    snapshot_entries.append(entry)

        # .mcp.json is the single MCP-config write: the generator emits it from
        # the workspace's servers; here we guarantee it exists (Claude's
        # --strict-mcp-config errors if absent) and merge in the run-scoped
        # intrinsic servers (host_env / agent_tools) — one writer, no post-render
        # patch.
        mcp_json = target_dir / MCP_FILENAME
        if mcp_json.exists():
            mcp_data = json.loads(mcp_json.read_text(encoding="utf-8"))
        else:
            mcp_data = {"mcpServers": {}}
        mcp_data.setdefault("mcpServers", {})
        for name, spec in (extra_mcp_servers or {}).items():
            mcp_data["mcpServers"][name] = spec
        mcp_json.write_text(
            json.dumps(mcp_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

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
