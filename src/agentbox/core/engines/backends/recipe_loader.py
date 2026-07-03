"""Recipe loader — bridges the backend registry and the Recipe value type.

``load_recipe``, ``list_recipes``, and ``backend_for_engine`` live here
(not in ``workspaces.generation.recipe``) because they need the backend
registry. ``workspaces.*`` callers (build.py, prep.py, service) import
directly from this module; the CLI routes through ``WorkspaceService``.
"""

from __future__ import annotations

import yaml

from agentbox.core.data.workenv import Recipe
from agentbox.core.engines.backends import get_backend, list_backends


def backend_for_engine(engine: str):
    """Return the registered backend instance for *engine*.

    Recipe engine names match backend entry-point names directly.
    Raises ``KeyError`` if no backend is registered.
    """
    return get_backend(engine)


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
