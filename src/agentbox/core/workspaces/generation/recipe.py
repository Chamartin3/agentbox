"""Recipe — engine layout described as YAML data, not code."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from agentbox.core.engines.backends import get_backend, list_backends


def backend_for_engine(engine: str):
    """Return the registered backend for a recipe *engine* name.

    Recipe engine names match backend entry-point names directly.
    Raises ``KeyError`` if no backend is registered.
    """
    return get_backend(engine)


@dataclass(frozen=True)
class Recipe:
    """Engine-specific workspace layout.

    Loaded from a backend's ``recipe.yaml`` file.
    """

    engine: str
    recipe_dir: Path
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
        full_path = self.recipe_dir / tmpl_path
        if not full_path.is_file():
            return None
        return full_path.read_text(encoding="utf-8")


def load_recipe(engine: str) -> Recipe:
    """Load a recipe from the backend package registered for *engine*."""
    try:
        recipe_path = get_backend(engine).recipe_path()
    except KeyError:
        recipe_path = None
    if recipe_path is None or not recipe_path.is_file():
        raise FileNotFoundError(f"No recipe for engine: {engine}")
    data = yaml.safe_load(recipe_path.read_text(encoding="utf-8"))
    return Recipe(
        engine=data.get("engine", engine),
        recipe_dir=recipe_path.parent,
        layout=data.get("layout", {}),
        serialization=data.get("serialization", {}),
        templates=data.get("templates", {}),
    )


def list_recipes() -> list[str]:
    """List available engine recipes (``claude_code``, ``opencode``, …)."""
    engines: list[str] = []
    for backend_name in list_backends():
        backend = get_backend(backend_name)
        # Defensive: test fixtures may swap in a minimal fake backend.
        if not hasattr(backend, "recipe_path"):
            continue
        recipe_path = backend.recipe_path()
        if recipe_path is not None and recipe_path.is_file():
            engines.append(backend_name)
    return sorted(engines)
