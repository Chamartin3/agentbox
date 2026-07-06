"""Materialize workspace file bindings into a run's workdir.

Higher-level wrapper over :mod:`agentbox.core.workspaces.generation.blobs`
that understands the binding metadata: ``target_path`` defaults,
``materialize_mode`` (copy / symlink), ``on_conflict`` policy, and
``role="workspace_file"`` snapshot entries.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

from agentbox.core.data.constants import ResourceType
from agentbox.core.data.workenv import Recipe
from agentbox.core.data.workenv import MaterializeOutcome as MaterializeOutcome
from agentbox.core.workspaces.generation.blobs import materialize_blobs
from agentbox.core.workspaces.generation._paths import safe_dest


def _resolve_single_file_name(
    *,
    resource_type: str,
    display_name: str,
    source_metadata: dict | None,
) -> str:
    """Pick the filename for a single-blob resource.

    Precedence:
      1. ``source_metadata.filename`` — exact name of the file that was
         imported. Respects the original extension.
      2. ``source_metadata.host_path`` — basename of the host path.
      3. ``display_name`` — used as-is if it already has an extension;
         otherwise the type's default extension is appended.
    """
    meta = source_metadata or {}
    filename = meta.get("filename")
    if isinstance(filename, str) and filename.strip():
        return Path(filename).name
    host_path = meta.get("host_path")
    if isinstance(host_path, str) and host_path.strip():
        return Path(host_path).name
    name = display_name.strip()
    if not name:
        name = "document"
    if "." not in Path(name).name:
        name += ResourceType(resource_type).default_extension
    return Path(name).name


def _skill_targets(b: dict, recipes: Iterable[Recipe]) -> list[str]:
    """Skill dirs across every engine whose recipe declares a skill layout.

    Skill placement is harness-specific, so the path comes from each
    backend's ``recipe.yaml`` (``layout.skill``), never a hardcoded default.
    An explicit ``target_path`` overrides. The recipe pattern names the
    SKILL.md file (e.g. ``.claude/skills/{name}/SKILL.md``); the materializer
    writes the blob tree into its parent dir. Backends with no ``skill:``
    entry contribute nothing — an empty result means "no engine supports
    skills", and the binding is skipped rather than silently dropped in a
    claude-shaped path.
    """
    if b.get("target_path"):
        return [b["target_path"]]
    name = (b.get("skill_meta") or {}).get("skill_name") or (b.get("display_name") or "")
    targets: list[str] = []
    for r in recipes:
        pattern = r.resolve_layout("skill", name=name)
        if pattern:
            targets.append(str(PurePosixPath(pattern).parent))
    return targets


def _resolve_target_path(b: dict) -> str:
    """Return the final relative target path for a non-skill binding.

    Semantics:
      - ``folder``: ``target_path`` IS the destination directory (or
        ``display_name`` if null).
      - single-file types (document/schema/script): ``target_path`` is a
        FOLDER; the filename is resolved from the source. Null target_path
        means "drop at workspace root".

    Skills are placed per-engine via :func:`_skill_targets`.
    """
    resource_type = b["type"]
    display_name = b.get("display_name", "") or ""
    target_path = b.get("target_path")
    if ResourceType(resource_type).is_single_file:
        filename = _resolve_single_file_name(
            resource_type=resource_type,
            display_name=display_name,
            source_metadata=b.get("source_metadata"),
        )
        folder = (target_path or "").strip("/")
        return f"{folder}/{filename}" if folder else filename
    # folder / other multi-blob types
    return target_path or display_name




def _materialize_one(
    b: dict, workdir: Path, target_rel: str, *, cache_root: Path | None
) -> MaterializeOutcome:
    """Write a single binding's blobs to one destination under ``workdir``."""
    dest = safe_dest(workdir, target_rel)
    on_conflict = b.get("on_conflict", "error")
    if dest.exists():
        if on_conflict == "error":
            raise FileExistsError(
                f"binding {b['binding_id']}: target {target_rel!r} already exists"
            )
        if on_conflict == "skip":
            return MaterializeOutcome(
                binding_id=b["binding_id"],
                resource_id=b["resource_id"],
                version_id=b["version_id"],
                content_hash=b["content_hash"],
                target_path=target_rel,
                files_written=0,
                mode=b.get("materialize_mode", "symlink"),
                skipped=True,
                skipped_reason="target exists, on_conflict=skip",
            )

    mode = b.get("materialize_mode", "symlink")
    if mode == "symlink" and cache_root is not None:
        cache_dir = cache_root / b["version_id"]
        if not cache_dir.exists():
            materialize_blobs(b["blobs"], cache_dir, overwrite=True)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() or dest.is_symlink():
            if dest.is_dir() and not dest.is_symlink():
                raise FileExistsError(
                    f"binding {b['binding_id']}: cannot symlink over real directory at {target_rel!r}"
                )
            dest.unlink()
        os.symlink(cache_dir, dest)
        written_count = sum(1 for _ in cache_dir.rglob("*") if _.is_file())
        return MaterializeOutcome(
            binding_id=b["binding_id"],
            resource_id=b["resource_id"],
            version_id=b["version_id"],
            content_hash=b["content_hash"],
            target_path=target_rel,
            files_written=written_count,
            mode="symlink",
        )

    # copy (default) — also the fallback for symlink without cache_root
    written = materialize_blobs(b["blobs"], dest, overwrite=(on_conflict == "overwrite"))
    return MaterializeOutcome(
        binding_id=b["binding_id"],
        resource_id=b["resource_id"],
        version_id=b["version_id"],
        content_hash=b["content_hash"],
        target_path=target_rel,
        files_written=len(written),
        mode="copy",
    )


def materialize_workspace(
    workdir: Path,
    resolved_bindings: Iterable[dict],
    *,
    recipes: Iterable[Recipe] = (),
    cache_root: Path | None = None,
) -> list[MaterializeOutcome]:
    """Write each binding's blobs into ``workdir``.

    Each entry in ``resolved_bindings`` must include:
        binding_id, resource_id, version_id, content_hash, type,
        display_name, target_path (nullable), materialize_mode,
        on_conflict, blobs (list of blob dicts), skill_meta (optional).

    ``recipes`` are the active backends' layout recipes. Skill bindings are
    placed into every engine that declares a ``layout.skill`` path (yielding
    one outcome per engine); all other types are written once. A skill with
    no supporting engine is reported as a skipped outcome.
    """
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    recipes = list(recipes)
    outcomes: list[MaterializeOutcome] = []
    for b in resolved_bindings:
        if b["type"] == "skill":
            targets = _skill_targets(b, recipes)
            if not targets:
                outcomes.append(
                    MaterializeOutcome(
                        binding_id=b["binding_id"],
                        resource_id=b["resource_id"],
                        version_id=b["version_id"],
                        content_hash=b["content_hash"],
                        target_path="",
                        files_written=0,
                        mode=b.get("materialize_mode", "symlink"),
                        skipped=True,
                        skipped_reason="no active engine declares a skill layout",
                    )
                )
                continue
        else:
            targets = [_resolve_target_path(b)]
        for target_rel in targets:
            outcomes.append(_materialize_one(b, workdir, target_rel, cache_root=cache_root))
    return outcomes
