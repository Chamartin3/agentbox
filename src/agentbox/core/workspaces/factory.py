"""Workspace constructor factory — wires the backend registry into generation.

This module lives in the workspaces layer (which may import both
``core.engines`` and ``core.workspaces.generation``) so that
``recipe_loader`` does not reach up into the workspaces domain.

All top-level imports; no nested or conditional imports.
"""

from __future__ import annotations

from agentbox.core.engines.backends.recipe_loader import (
    backend_for_engine,
    list_recipes,
    load_recipe,
)
from agentbox.core.workspaces.generation import (
    Item,
    WorkspaceConfig,
    WorkspaceConstructor,
)


def native_extra_items(engine: str, config: WorkspaceConfig) -> list[Item]:
    """Per-engine native config items (opencode.json, codex TOML, …).

    Needs the backend registry; lives here (workspaces layer) so that
    ``recipe_loader`` (engines layer) stays free of workspaces imports.
    """
    try:
        return backend_for_engine(engine).build_workspace_items(config)
    except KeyError:
        return []


def workspace_constructor() -> WorkspaceConstructor:
    """A ``WorkspaceConstructor`` wired to every registered engine recipe."""
    return WorkspaceConstructor(
        [load_recipe(e) for e in list_recipes()],
        extra_items=native_extra_items,
    )
