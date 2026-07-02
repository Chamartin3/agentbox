"""Preset management for WorkenvConfig generation.

Seeds are loaded from YAML files under ``seeds/``.  The DB is authoritative
— re-running the loader is idempotent and does **not** clobber edits.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from agentbox.core.constants import BackendName
from agentbox.core.db import WorkenvTemplateManager
from agentbox.core.workspaces.generation.config import WorkenvConfig

_SEEDS_DIR = Path(__file__).parent / "seeds"


def list_presets(templates_mgr: WorkenvTemplateManager) -> list[dict]:
    """List all templates in the DB as summary dicts."""
    return templates_mgr.list_all()


def from_preset(templates_mgr: WorkenvTemplateManager, name: str) -> WorkenvConfig | None:
    """Load a ``WorkenvConfig`` from a named preset in the DB.

    Returns ``None`` if *name* is not found.
    """
    row = templates_mgr.get_by_name(name)
    if row is None:
        return None
    raw = row.get("config_json")
    if isinstance(raw, str):
        raw = json.loads(raw)
    return WorkenvConfig.from_yaml(yaml.dump(raw, sort_keys=False))


def save_as_preset(
    templates_mgr: WorkenvTemplateManager,
    name: str,
    config: WorkenvConfig,
    *,
    engine: str = BackendName.CLAUDE_CODE,
    description: str | None = None,
) -> dict:
    """Persist a ``WorkenvConfig`` as a named template."""
    config_json = json.loads(json.dumps(config._to_dict()))
    return templates_mgr.upsert(
        name,
        engine=engine,
        config_json=config_json,
        description=description or config.description,
    )


def load_seed_templates() -> list[dict]:
    """Load all seed YAML files from ``seeds/``."""
    if not _SEEDS_DIR.is_dir():
        return []
    templates: list[dict] = []
    for path in sorted(_SEEDS_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if data:
            templates.append(data)
    return templates


def seed_presets(templates_mgr: WorkenvTemplateManager) -> int:
    """Idempotently seed built-in presets into the DB.

    Returns the number of templates seeded (existing ones are skipped).
    """
    templates = load_seed_templates()
    return templates_mgr.seed(templates)
