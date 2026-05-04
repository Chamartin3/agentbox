"""Materialize workspace file bindings into a run's workdir (Plan 03).

Higher-level wrapper over :mod:`agentbox.core.resources.materializer`
that understands the binding metadata: ``target_path`` defaults,
``materialize_mode`` (copy / symlink), ``on_conflict`` policy, and
``role="workspace_file"`` snapshot entries.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from agentbox.core.resources.materializer import materialize_blobs

DEFAULT_SKILLS_ROOT = ".claude/skills"


@dataclass(frozen=True)
class MaterializeOutcome:
    binding_id: str
    resource_id: str
    version_id: str
    content_hash: str
    target_path: str
    files_written: int
    mode: str
    skipped: bool = False
    skipped_reason: str | None = None


def _default_target_path(resource_type: str, display_name: str, skill_meta: dict | None) -> str:
    if resource_type == "skill":
        name = (skill_meta or {}).get("skill_name") or display_name
        return f"{DEFAULT_SKILLS_ROOT}/{name}"
    return display_name


def _safe_target(workdir: Path, rel: str) -> Path:
    """Reject path-traversal attempts."""
    if rel.startswith("/"):
        raise ValueError(f"target_path {rel!r} must be relative")
    parts = [p for p in rel.split("/") if p]
    if any(p == ".." for p in parts):
        raise ValueError(f"target_path {rel!r} must not contain '..'")
    out = (workdir / Path(*parts)).resolve()
    if not str(out).startswith(str(workdir.resolve())):
        raise ValueError(f"target_path {rel!r} escapes workdir")
    return out


def materialize_workspace(
    workdir: Path,
    resolved_bindings: Iterable[dict],
    *,
    cache_root: Path | None = None,
) -> list[MaterializeOutcome]:
    """Write each binding's blobs into ``workdir``.

    Each entry in ``resolved_bindings`` must include:
        binding_id, resource_id, version_id, content_hash, type,
        display_name, target_path (nullable), materialize_mode,
        on_conflict, blobs (list of blob dicts), skill_meta (optional).
    """
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    outcomes: list[MaterializeOutcome] = []
    for b in resolved_bindings:
        target_rel = b.get("target_path") or _default_target_path(
            b["type"], b.get("display_name", ""), b.get("skill_meta")
        )
        dest = _safe_target(workdir, target_rel)
        on_conflict = b.get("on_conflict", "error")
        if dest.exists():
            if on_conflict == "error":
                raise FileExistsError(
                    f"binding {b['binding_id']}: target {target_rel!r} already exists"
                )
            if on_conflict == "skip":
                outcomes.append(
                    MaterializeOutcome(
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
                )
                continue

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
            outcomes.append(
                MaterializeOutcome(
                    binding_id=b["binding_id"],
                    resource_id=b["resource_id"],
                    version_id=b["version_id"],
                    content_hash=b["content_hash"],
                    target_path=target_rel,
                    files_written=written_count,
                    mode="symlink",
                )
            )
            continue

        # copy (default) — also the fallback for symlink without cache_root
        written = materialize_blobs(b["blobs"], dest, overwrite=(on_conflict == "overwrite"))
        outcomes.append(
            MaterializeOutcome(
                binding_id=b["binding_id"],
                resource_id=b["resource_id"],
                version_id=b["version_id"],
                content_hash=b["content_hash"],
                target_path=target_rel,
                files_written=len(written),
                mode="copy",
            )
        )
    return outcomes
