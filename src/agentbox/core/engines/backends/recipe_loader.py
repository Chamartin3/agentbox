"""Recipe loader — bridges the backend registry and the Recipe value type.

``load_recipe``, ``list_recipes``, and ``backend_for_engine`` live here
(not in ``core.data.workenv``) because they need the backend
registry. ``workspaces.*`` callers (build.py, prep.py, service) import
directly from this module; the CLI routes through ``WorkspaceService``.

The workspace constructor factory (``workspace_constructor``,
``native_extra_items``) lives in ``core.workspaces.build`` — that
module is in the workspaces layer and may import both engines and
core.workspaces.build without layering violations.
"""

from __future__ import annotations

import yaml

from agentbox.core.data.workenv import Recipe
from agentbox.core.engines.backends import BackendAdapter, get_backend, list_backends


def backend_for_engine(engine: str) -> BackendAdapter:
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


def context_filenames() -> list[str]:
    """Instruction-file names each registered engine reads (``layout.context``).

    Claude → ``CLAUDE.md``, OpenCode/Codex → ``AGENTS.md``. Sourced from the
    recipes so the set is never hardcoded.
    """
    names = {load_recipe(e).layout.get("context") for e in list_recipes()}
    return sorted(n for n in names if n)


def engine_artifact_paths() -> tuple[frozenset[str], frozenset[str]]:
    """Files/dirs the builder writes for every engine, read from each recipe's
    ``layout`` so the set tracks the registered backends automatically.

    Returns ``(root_files, dir_prefixes)``. A layout value is a path template
    for an artifact the builder materializes (``CLAUDE.md``, ``.mcp.json``,
    ``.claude/agents/{name}.md`` …). Root-level filenames become exact-match
    ``root_files``; any nested or per-``{name}`` path contributes its
    top-level directory (``.claude/``, ``.opencode/``, ``.codex/``) as a
    ``dir_prefix``.
    """
    root_files: set[str] = set()
    dir_prefixes: set[str] = set()
    for engine in list_recipes():
        for value in load_recipe(engine).layout.values():
            if not value:
                continue
            head = value.split("{", 1)[0]  # drop per-name placeholder tail
            if "/" in head:
                dir_prefixes.add(head.split("/", 1)[0] + "/")
            else:
                root_files.add(head)
    return frozenset(root_files), frozenset(dir_prefixes)


