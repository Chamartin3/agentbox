"""Boot-time resource reconciliation: bulk imports from on-disk layout."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from agentbox.core.data.constants import ResourceType
from agentbox.core.db import (
    ResourceManager,
    ResourceVersionManager,
)
from agentbox.core.resources.boot.discover import resolve_skill_roots
from agentbox.core.resources.boot.import_one import _import_one, import_one_skill
from agentbox.core.resources.importers.host_path import HostPathImporter
from agentbox.core.resources.importers.schema import SchemaImporter

logger = logging.getLogger(__name__)

DEFAULT_AGENTS_DIR = "agents"
DEFAULT_SHARED_DIR = "shared"


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
