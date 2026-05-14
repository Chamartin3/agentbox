"""Boot-time importer for the central resource repository (Plan 01 §Migration,
Plan 03 §Migration).

Populates ``repo_resources`` from the on-disk manifest layout:

* ``apps/cvman/mcp/skills/<name>/``        → type=skill (via SkillImporter)
* ``agents/<id>/output_schema.json``       → type=document
* ``agents/<id>/input_schema.json``        → type=document
* ``agents/<id>/prompts/system.md``        → type=document
* ``shared/<scope>/`` (each top-level dir) → type=folder (via HostPathImporter)

Also creates ``workspace_file_resource_bindings`` for each manifest-declared
``[[workspaces]] skills = […]`` entry (target_path=.claude/skills/<name>,
materialize_mode=symlink), but only when the workspace has no existing
bindings (so it never tramples operator changes).

Idempotent: a resource whose slug already exists with a matching active
content hash is skipped. New on-disk content yields a new version.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from agentbox.core.constants import ResourceType
from agentbox.core.data.resources import _hash_blobs
from agentbox.core.resources.importers.base import ImporterContext
from agentbox.core.resources.importers.host_path import HostPathImporter
from agentbox.core.resources.importers.schema import SchemaImporter
from agentbox.core.resources.importers.skill import SkillImporter

if TYPE_CHECKING:
    from agentbox.core.data.store import SessionStore

logger = logging.getLogger(__name__)

DEFAULT_SKILLS_SOURCES: list[str] = [
    "apps/cvman/mcp/skills",
    "agentbox/skills",
    "skills",
]
DEFAULT_AGENTS_DIR = "agents"
DEFAULT_SHARED_DIR = "shared"
DEFAULT_BINDING_REASON = "boot-time migration from manifest"

_SKILL_ROOT_SKIP_PARTS = frozenset({".venv", "node_modules", ".git"})
_SKILL_ROOT_SKIP_SUFFIXES = ("workdir/worktrees",)


def _is_skipped_skill_root(p: Path) -> bool:
    """Return True if ``p`` lives under a vendor/transient location."""
    parts = p.parts
    if any(part in _SKILL_ROOT_SKIP_PARTS for part in parts):
        return True
    s = str(p).replace(os.sep, "/")
    return any(suffix in s for suffix in _SKILL_ROOT_SKIP_SUFFIXES)


def resolve_skill_roots(root: Path) -> list[Path]:
    """Return the ordered list of existing skill roots to scan.

    Combines :data:`DEFAULT_SKILLS_SOURCES` with paths from the
    ``AGENTBOX_EXTRA_SKILL_ROOTS`` env var (``:``-separated). Each extra
    root may be absolute or relative to ``root``. Vendor/transient paths
    (.venv, node_modules, .git, workdir/worktrees) are filtered out.
    """
    candidates: list[Path] = [root / rel for rel in DEFAULT_SKILLS_SOURCES]
    extra = os.environ.get("AGENTBOX_EXTRA_SKILL_ROOTS", "")
    for token in extra.split(":"):
        token = token.strip()
        if not token:
            continue
        p = Path(token)
        if not p.is_absolute():
            p = root / p
        candidates.append(p)

    seen: set[Path] = set()
    out: list[Path] = []
    for c in candidates:
        try:
            resolved = c.resolve() if c.exists() else c
        except OSError:
            resolved = c
        if resolved in seen:
            continue
        seen.add(resolved)
        if not c.is_dir():
            continue
        if _is_skipped_skill_root(c):
            continue
        out.append(c)
    return out


def import_one_skill(
    store: SessionStore, skill_dir: Path, root: Path
) -> tuple[str, str]:
    """Create-or-update a single ``skill:<name>`` resource. Returns (action, slug)."""
    name = skill_dir.name
    slug = f"skill:{name}"
    try:
        rel = skill_dir.relative_to(root)
        desc = f"Imported from {rel}"
    except ValueError:
        desc = f"Imported from {skill_dir}"
    action, _ = _import_one(
        store,
        slug=slug,
        type_=ResourceType.SKILL,
        display_name=name,
        description=desc,
        importer=SkillImporter(root=skill_dir),
        tags=("skill", name),
    )
    return action, slug


def _import_one(
    store: SessionStore,
    *,
    slug: str,
    type_: ResourceType | str,
    display_name: str,
    description: str,
    importer,
    tags: Iterable[str] = (),
    metadata_extra: dict | None = None,
) -> tuple[str, bool]:
    """Idempotently create-or-update a single resource. Returns (action, slug).

    action ∈ {"created", "updated", "skipped"}.
    """
    ctx = ImporterContext(actor="boot_sweep", changelog="imported from manifest layout")
    result = importer.run(ctx)
    content_hash = _hash_blobs((b[0], b[1]) for b in result.blobs)

    merged_metadata = dict(result.metadata or {})
    if metadata_extra:
        merged_metadata.update(metadata_extra)

    existing = store.get_repo_resource_by_slug(slug)
    if existing is not None:
        if existing.get("type") != type_:
            store.update_repo_resource(existing["id"], type=type_)
        active = store.get_active_repo_version(existing["id"])
        if active and active.get("content_hash") == content_hash:
            return "skipped", slug
        store.import_repo_version(
            existing["id"],
            result.blobs,
            import_source="toml_migration",
            changelog="updated from manifest layout",
            source_metadata=result.source_metadata,
            metadata=merged_metadata or None,
        )
        return "updated", slug

    row = store.create_repo_resource(
        slug=slug,
        type=type_,
        display_name=display_name,
        description=description,
        tags=list(tags) or None,
    )
    store.import_repo_version(
        row["id"],
        result.blobs,
        import_source="toml_migration",
        changelog="initial import from manifest layout",
        source_metadata=result.source_metadata,
        metadata=merged_metadata or None,
    )
    return "created", slug


def import_repo_resources(store: SessionStore, root: Path) -> dict:
    """Run all repo_resources sweeps. Returns a summary dict."""
    if not root.exists():
        return {"created": 0, "updated": 0, "skipped": 0, "failed": 0}

    created = updated = skipped = failed = 0

    def _safe(slug: str, fn) -> None:
        nonlocal created, updated, skipped, failed
        try:
            action, _ = fn()
            if action == "created":
                created += 1
            elif action == "updated":
                updated += 1
            else:
                skipped += 1
        except Exception:
            failed += 1
            logger.exception("boot-import: failed for %r", slug)

    # 1) Skills — one resource per skill folder, across multiple roots.
    seen_skill_names: dict[str, Path] = {}
    for skills_root in resolve_skill_roots(root):
        for skill_dir in sorted(skills_root.iterdir()):
            if not skill_dir.is_dir() or not (skill_dir / "SKILL.md").is_file():
                continue
            name = skill_dir.name
            if name in seen_skill_names:
                logger.warning(
                    "boot-import skills: duplicate skill %r at %s (already imported from %s) — skipping",
                    name, skill_dir, seen_skill_names[name],
                )
                continue
            seen_skill_names[name] = skill_dir
            slug = f"skill:{name}"
            _safe(slug, lambda d=skill_dir, r=root: import_one_skill(store, d, r))

    # 2) Agent schemas (single-file documents).
    agents_root = root / DEFAULT_AGENTS_DIR
    if agents_root.is_dir():
        for agent_dir in sorted(agents_root.iterdir()):
            if not agent_dir.is_dir():
                continue
            for fname, tag in (
                ("output_schema.json", "output_schema"),
                ("input_schema.json", "input_schema"),
            ):
                fpath = agent_dir / fname
                if not fpath.is_file():
                    continue
                slug = f"agent/{agent_dir.name}/{fname.removesuffix('.json')}"
                try:
                    content = fpath.read_bytes()
                    schema_importer = SchemaImporter(
                        filename=fname, content=content, import_source="toml_migration",
                    )
                    _safe(slug, lambda s=slug, n=agent_dir.name, t=tag, imp=schema_importer, p=fpath: _import_one(
                        store, slug=s, type_="schema",
                        display_name=f"{n} {t}",
                        description=f"Imported from {p.relative_to(root)}",
                        importer=imp,
                        tags=(t, n),
                        metadata_extra={"role": t, "agent_id": n},
                    ))
                except (OSError, ValueError):
                    # Fall back to document type if schema parse fails — still surface it.
                    _safe(slug, lambda p=fpath, s=slug, n=agent_dir.name, t=tag: _import_one(
                        store, slug=s, type_="document",
                        display_name=f"{n} {t}",
                        description=f"Imported from {p.relative_to(root)}",
                        importer=HostPathImporter(root=p),
                        tags=(t, n),
                        metadata_extra={"role": t, "agent_id": n, "schema_parse_failed": True},
                    ))
            sys_prompt = agent_dir / "prompts" / "system.md"
            if sys_prompt.is_file():
                slug = f"agent/{agent_dir.name}/system_prompt"
                _safe(slug, lambda p=sys_prompt, s=slug, n=agent_dir.name: _import_one(
                    store, slug=s, type_=ResourceType.DOCUMENT,
                    display_name=f"{n} system prompt",
                    description=f"Imported from {p.relative_to(root)}",
                    importer=HostPathImporter(root=p),
                    tags=("system_prompt", n),
                    metadata_extra={"role": "system_fragment", "agent_id": n},
                ))

    # 3) Shared scopes — one folder resource per top-level subdirectory.
    shared_root = root / DEFAULT_SHARED_DIR
    if shared_root.is_dir():
        for scope_dir in sorted(shared_root.iterdir()):
            if not scope_dir.is_dir():
                continue
            slug = f"shared:{scope_dir.name}"
            _safe(slug, lambda d=scope_dir, s=slug: _import_one(
                store, slug=s, type_=ResourceType.FOLDER,
                display_name=d.name,
                description=f"Imported from {d.relative_to(root)}",
                importer=HostPathImporter(root=d),
                tags=("reference", d.name),
            ))

    summary = {"created": created, "updated": updated, "skipped": skipped, "failed": failed}
    logger.info("boot-import repo_resources: %s", summary)
    return summary


def sweep_workspace_skill_bindings(store: SessionStore, manifest) -> dict:
    """Convert manifest-declared workspace skills into workspace_file_resource_bindings.

    Per Plan 03 §Migration: each ``[[workspaces]] skills = [...]`` entry becomes
    a workspace_file_resource_binding with ``target_path=.claude/skills/<name>``
    and ``materialize_mode=symlink``. Only runs for workspaces that have **no**
    existing bindings — never overwrites operator changes.
    """
    if manifest is None or not getattr(manifest, "workspaces", None):
        return {"workspaces_wired": 0, "bindings_added": 0}

    workspaces_wired = 0
    bindings_added = 0

    for ws in manifest.workspaces:
        skills = list(getattr(ws, "skills", None) or [])
        if not skills:
            continue
        existing = store.list_workspace_file_bindings(ws.name)
        if existing:
            continue

        bindings = []
        for skill_name in skills:
            res = store.get_repo_resource_by_slug(f"skill:{skill_name}")
            if res is None:
                logger.warning(
                    "boot-import bindings: workspace %r references missing skill %r",
                    ws.name, skill_name,
                )
                continue
            bindings.append({
                "resource_id": res["id"],
                "target_path": f".claude/skills/{skill_name}",
                "materialize_mode": "symlink",
                "on_conflict": "overwrite",
            })

        if not bindings:
            continue
        try:
            store.replace_workspace_file_bindings(
                ws.name, bindings, reason=DEFAULT_BINDING_REASON, actor="boot_sweep",
            )
            workspaces_wired += 1
            bindings_added += len(bindings)
        except Exception:
            logger.exception("boot-import bindings: failed for workspace %r", ws.name)

    summary = {"workspaces_wired": workspaces_wired, "bindings_added": bindings_added}
    logger.info("boot-import workspace bindings: %s", summary)
    return summary


# ---------------------------------------------------------------------------
# Composition references → per-file document resources + prompt bindings
# ---------------------------------------------------------------------------


def _slug_for_ref_path(path_str: str, bundle_rel: str | None) -> str:
    """Derive a stable resource slug from a composition reference path.

    ``shared://drafting/guidelines_v2/foo.md`` → ``shared:drafting/guidelines_v2/foo.md``
    ``prompts/refs/voice.md`` (bundle-relative, agent_id=draft.writer) →
        ``agent/draft.writer/prompts/refs/voice.md``
    """
    if path_str.startswith("shared://"):
        return f"shared:{path_str[len('shared://'):]}"
    return f"agent/{bundle_rel}/{path_str}" if bundle_rel else path_str


def _resolve_ref_file(path_str: str, project_root: Path, bundle_dir: Path | None) -> Path | None:
    """Return the absolute path for a composition reference entry.

    Returns None when the file cannot be located on disk.
    """
    if path_str.startswith("shared://"):
        candidate = project_root / "shared" / path_str[len("shared://"):]
    elif bundle_dir is not None:
        candidate = bundle_dir / path_str
    else:
        candidate = project_root / path_str
    return candidate if candidate.is_file() else None


def import_composition_references(store: SessionStore, root: Path, manifest) -> dict:
    """Auto-import each agent's ``[composition].references`` as per-file
    document resources, and wire them as ``attach_as_reference`` prompt
    bindings on the agent.

    Only runs for agents that have **no** existing prompt bindings — never
    trampling operator changes via the UI. Idempotent: existing resource
    rows with matching content hashes are reused.
    """
    if manifest is None or not getattr(manifest, "agents", None):
        return {"agents_wired": 0, "resources_created": 0, "bindings_added": 0}

    agents_wired = 0
    resources_created = 0
    bindings_added = 0

    for agent in manifest.agents:
        comp = getattr(agent, "composition", None)
        if not comp or not getattr(comp, "references", None):
            continue
        existing = store.list_prompt_bindings(agent.id)
        if existing:
            continue

        bundle_dir: Path | None = None
        if getattr(agent, "source_path", None):
            bundle_dir = Path(agent.source_path).parent

        bindings: list[dict] = []
        for idx, ref in enumerate(comp.references):
            if isinstance(ref, str):
                path_str = ref
            elif isinstance(ref, dict):
                path_str = ref.get("path", "")
            else:
                shared_id = getattr(ref, "shared", None)
                if not shared_id:
                    continue
                existing_res = store.get_repo_resource_by_slug(f"shared:{shared_id}")
                if existing_res is None:
                    logger.warning(
                        "boot-import refs: agent %s references missing shared resource %r",
                        agent.id, shared_id,
                    )
                    continue
                bindings.append({
                    "resource_id": existing_res["id"],
                    "marker": f"ref_{idx}",
                    "mode": "inline",
                    "attach_as_reference": True,
                    "required": False,
                    "display_order": idx,
                })
                continue

            if not path_str:
                continue

            slug_path_arg = agent.id if not path_str.startswith("shared://") else None
            slug = _slug_for_ref_path(path_str, slug_path_arg)
            fpath = _resolve_ref_file(path_str, root, bundle_dir)
            if fpath is None:
                logger.warning(
                    "boot-import refs: agent %s reference %r not found on disk",
                    agent.id, path_str,
                )
                continue

            display_name = fpath.stem.replace("_", " ").replace("-", " ").title()

            def _do_doc(p=fpath, s=slug, dn=display_name):
                return _import_one(
                    store, slug=s, type_=ResourceType.DOCUMENT,
                    display_name=dn,
                    description=f"Imported from {p.relative_to(root)}"
                        if root in p.parents else f"Imported from {p}",
                    importer=HostPathImporter(root=p),
                    tags=("reference",),
                )

            try:
                action, _ = _do_doc()
                if action == "created":
                    resources_created += 1
            except Exception:
                logger.exception(
                    "boot-import refs: failed to import %r for agent %s",
                    path_str, agent.id,
                )
                continue

            res = store.get_repo_resource_by_slug(slug)
            if res is None:
                continue
            bindings.append({
                "resource_id": res["id"],
                "marker": f"ref_{idx}",
                "mode": "inline",
                "attach_as_reference": True,
                "required": False,
                "display_order": idx,
            })

        if not bindings:
            continue
        try:
            store.replace_prompt_bindings(
                agent.id, bindings,
                reason="boot: auto-imported from composition.references",
                actor="boot_sweep",
            )
            agents_wired += 1
            bindings_added += len(bindings)
        except Exception:
            logger.exception(
                "boot-import refs: failed to write bindings for agent %s", agent.id,
            )

    summary = {
        "agents_wired": agents_wired,
        "resources_created": resources_created,
        "bindings_added": bindings_added,
    }
    logger.info("boot-import composition references: %s", summary)
    return summary
