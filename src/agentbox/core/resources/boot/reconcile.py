"""Boot-time resource reconciliation: bulk imports, bindings, and refs."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from agentbox.core.constants import ResourceType
from agentbox.core.data.manifests.system import ProjectManifest
from agentbox.core.db import (
    AgentPromptResourceBindingManager,
    ResourceManager,
    ResourceVersionManager,
    WorkspaceFileResourceBindingManager,
)
from agentbox.core.resources.boot.discover import resolve_skill_roots
from agentbox.core.resources.boot.import_one import _import_one, import_one_skill
from agentbox.core.resources.importers.host_path import HostPathImporter
from agentbox.core.resources.importers.schema import SchemaImporter

logger = logging.getLogger(__name__)

DEFAULT_AGENTS_DIR = "agents"
DEFAULT_SHARED_DIR = "shared"
DEFAULT_BINDING_REASON = "boot-time migration from manifest"


def import_repo_resources(
    resources: ResourceManager,
    resource_versions: ResourceVersionManager,
    root: Path,
) -> dict:
    if not root.exists():
        return {"created": 0, "updated": 0, "skipped": 0, "failed": 0}
    created = updated = skipped = failed = 0

    def _safe(slug: str, fn: Callable[[], tuple[str, str]]) -> None:
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

    seen_skill_names: dict[str, Path] = {}
    for skills_root in resolve_skill_roots(root):
        for skill_dir in sorted(skills_root.iterdir()):
            if not skill_dir.is_dir() or not (skill_dir / "SKILL.md").is_file():
                continue
            name = skill_dir.name
            if name in seen_skill_names:
                logger.warning("boot-import skills: duplicate skill %r at %s (already imported from %s) — skipping", name, skill_dir, seen_skill_names[name])
                continue
            seen_skill_names[name] = skill_dir
            slug = f"skill:{name}"
            _safe(slug, lambda d=skill_dir, r=root: import_one_skill(resources, resource_versions, d, r))

    agents_root = root / DEFAULT_AGENTS_DIR
    if agents_root.is_dir():
        for agent_dir in sorted(agents_root.iterdir()):
            if not agent_dir.is_dir():
                continue
            for fname, tag in (("output_schema.json", "output_schema"), ("input_schema.json", "input_schema")):
                fpath = agent_dir / fname
                if not fpath.is_file():
                    continue
                slug = f"agent/{agent_dir.name}/{fname.removesuffix('.json')}"
                try:
                    content = fpath.read_bytes()
                    schema_importer = SchemaImporter(filename=fname, content=content, import_source="toml_migration")
                    _safe(slug, lambda s=slug, n=agent_dir.name, t=tag, imp=schema_importer, p=fpath: _import_one(resources, resource_versions, slug=s, type_="schema", display_name=f"{n} {t}", description=f"Imported from {p.relative_to(root)}", importer=imp, tags=(t, n), metadata_extra={"role": t, "agent_id": n}))
                except (OSError, ValueError):
                    _safe(slug, lambda p=fpath, s=slug, n=agent_dir.name, t=tag: _import_one(resources, resource_versions, slug=s, type_="document", display_name=f"{n} {t}", description=f"Imported from {p.relative_to(root)}", importer=HostPathImporter(root=p), tags=(t, n), metadata_extra={"role": t, "agent_id": n, "schema_parse_failed": True}))
            sys_prompt = agent_dir / "prompts" / "system.md"
            if sys_prompt.is_file():
                slug = f"agent/{agent_dir.name}/system_prompt"
                _safe(slug, lambda p=sys_prompt, s=slug, n=agent_dir.name: _import_one(resources, resource_versions, slug=s, type_=ResourceType.DOCUMENT, display_name=f"{n} system prompt", description=f"Imported from {p.relative_to(root)}", importer=HostPathImporter(root=p), tags=("system_prompt", n), metadata_extra={"role": "system_fragment", "agent_id": n}))

    shared_root = root / DEFAULT_SHARED_DIR
    if shared_root.is_dir():
        for scope_dir in sorted(shared_root.iterdir()):
            if not scope_dir.is_dir():
                continue
            slug = f"shared:{scope_dir.name}"
            _safe(slug, lambda d=scope_dir, s=slug: _import_one(resources, resource_versions, slug=s, type_=ResourceType.FOLDER, display_name=d.name, description=f"Imported from {d.relative_to(root)}", importer=HostPathImporter(root=d), tags=("reference", d.name)))

    summary = {"created": created, "updated": updated, "skipped": skipped, "failed": failed}
    logger.info("boot-import repo_resources: %s", summary)
    return summary


def sweep_workspace_skill_bindings(
    resources: ResourceManager,
    file_bindings: WorkspaceFileResourceBindingManager,
    manifest: ProjectManifest | None,
) -> dict:
    if manifest is None or not getattr(manifest, "workspaces", None):
        return {"workspaces_wired": 0, "bindings_added": 0}
    workspaces_wired = 0
    bindings_added = 0
    for ws in manifest.workspaces:
        skills = list(getattr(ws, "skills", None) or [])
        if not skills:
            continue
        existing = file_bindings.list_for_workspace(ws.name)
        if existing:
            continue
        bindings = []
        for skill_name in skills:
            res = resources.get_by_slug(f"skill:{skill_name}")
            if res is None:
                logger.warning("boot-import bindings: workspace %r references missing skill %r", ws.name, skill_name)
                continue
            bindings.append({"resource_id": res["id"], "target_path": f".claude/skills/{skill_name}", "materialize_mode": "symlink", "on_conflict": "overwrite"})
        if not bindings:
            continue
        try:
            file_bindings.replace_for_workspace(ws.name, bindings, reason=DEFAULT_BINDING_REASON, actor="boot_sweep")
            workspaces_wired += 1
            bindings_added += len(bindings)
        except Exception:
            logger.exception("boot-import bindings: failed for workspace %r", ws.name)
    summary = {"workspaces_wired": workspaces_wired, "bindings_added": bindings_added}
    logger.info("boot-import workspace bindings: %s", summary)
    return summary


def _slug_for_ref_path(path_str: str, bundle_rel: str | None) -> str:
    if path_str.startswith("shared://"):
        return f"shared:{path_str[len('shared://') :]}"
    return f"agent/{bundle_rel}/{path_str}" if bundle_rel else path_str


def _resolve_ref_file(path_str: str, project_root: Path, bundle_dir: Path | None) -> Path | None:
    if path_str.startswith("shared://"):
        candidate = project_root / "shared" / path_str[len("shared://") :]
    elif bundle_dir is not None:
        candidate = bundle_dir / path_str
    else:
        candidate = project_root / path_str
    return candidate if candidate.is_file() else None


def import_composition_references(
    resources: ResourceManager,
    resource_versions: ResourceVersionManager,
    prompt_bindings: AgentPromptResourceBindingManager,
    root: Path,
    manifest: ProjectManifest | None,
) -> dict:
    if manifest is None or not getattr(manifest, "agents", None):
        return {"agents_wired": 0, "resources_created": 0, "bindings_added": 0}
    agents_wired = 0
    resources_created = 0
    bindings_added = 0
    for agent in manifest.agents:
        comp = getattr(agent, "composition", None)
        if not comp or not getattr(comp, "references", None):
            continue
        existing = prompt_bindings.list_for_agent(agent.id)
        if existing:
            continue
        bundle_dir: Path | None = None
        source_path: str | None = getattr(agent, "source_path", None)
        if source_path:
            bundle_dir = Path(source_path).parent
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
                existing_res = resources.get_by_slug(f"shared:{shared_id}")
                if existing_res is None:
                    logger.warning("boot-import refs: agent %s references missing shared resource %r", agent.id, shared_id)
                    continue
                bindings.append({"resource_id": existing_res["id"], "marker": f"ref_{idx}", "mode": "inline", "attach_as_reference": True, "required": False, "display_order": idx})
                continue
            if not path_str:
                continue
            slug_path_arg = agent.id if not path_str.startswith("shared://") else None
            slug = _slug_for_ref_path(path_str, slug_path_arg)
            fpath = _resolve_ref_file(path_str, root, bundle_dir)
            if fpath is None:
                logger.warning("boot-import refs: agent %s reference %r not found on disk", agent.id, path_str)
                continue
            display_name = fpath.stem.replace("_", " ").replace("-", " ").title()

            def _do_doc(p: Path = fpath, s: str = slug, dn: str = display_name) -> tuple[str, str]:
                return _import_one(resources, resource_versions, slug=s, type_=ResourceType.DOCUMENT, display_name=dn, description=f"Imported from {p.relative_to(root)}" if root in p.parents else f"Imported from {p}", importer=HostPathImporter(root=p), tags=("reference",))
            try:
                action, _ = _do_doc()
                if action == "created":
                    resources_created += 1
            except Exception:
                logger.exception("boot-import refs: failed to import %r for agent %s", path_str, agent.id)
                continue
            res = resources.get_by_slug(slug)
            if res is None:
                continue
            bindings.append({"resource_id": res["id"], "marker": f"ref_{idx}", "mode": "inline", "attach_as_reference": True, "required": False, "display_order": idx})
        if not bindings:
            continue
        try:
            prompt_bindings.replace_for_agent(agent.id, bindings, reason="boot: auto-imported from composition.references", actor="boot_sweep")
            agents_wired += 1
            bindings_added += len(bindings)
        except Exception:
            logger.exception("boot-import refs: failed to write bindings for agent %s", agent.id)
    summary = {"agents_wired": agents_wired, "resources_created": resources_created, "bindings_added": bindings_added}
    logger.info("boot-import composition references: %s", summary)
    return summary
