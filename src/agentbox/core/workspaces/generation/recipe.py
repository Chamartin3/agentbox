"""Recipe — engine layout described as YAML data, not code."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

_RECIPES_ROOT = Path(__file__).parent / "recipes"


@dataclass(frozen=True)
class Recipe:
    """Engine-specific workspace layout.

    Loaded from a ``recipe.yaml`` file under ``recipes/<engine>/``.
    """

    engine: str
    layout: dict[str, str] = field(default_factory=dict)
    serialization: dict[str, str] = field(default_factory=dict)
    templates: dict[str, str] = field(default_factory=dict)

    def resolve_layout(self, role: str, **fmt_kwargs: str) -> str:
        """Resolve a layout path for *role*, formatting with *fmt_kwargs*."""
        pattern = self.layout.get(role, "")
        return pattern.format(**fmt_kwargs)

    def resolve_template(self, role: str) -> str | None:
        """Return the template content for *role*, or None."""
        tmpl_path = self.templates.get(role)
        if tmpl_path is None:
            return None
        recipe_dir = _RECIPES_ROOT / self.engine
        full_path = recipe_dir / tmpl_path
        if not full_path.is_file():
            return None
        return full_path.read_text(encoding="utf-8")


def load_recipe(engine: str) -> Recipe:
    """Load a recipe from ``recipes/<engine>/recipe.yaml``."""
    recipe_dir = _RECIPES_ROOT / engine
    recipe_file = recipe_dir / "recipe.yaml"
    if not recipe_file.is_file():
        raise FileNotFoundError(f"No recipe for engine: {engine}")
    data = yaml.safe_load(recipe_file.read_text(encoding="utf-8"))
    return Recipe(
        engine=data.get("engine", engine),
        layout=data.get("layout", {}),
        serialization=data.get("serialization", {}),
        templates=data.get("templates", {}),
    )


def list_recipes() -> list[str]:
    """List available engine recipes."""
    if not _RECIPES_ROOT.is_dir():
        return []
    return sorted(
        p.parent.name
        for p in _RECIPES_ROOT.rglob("recipe.yaml")
    )
