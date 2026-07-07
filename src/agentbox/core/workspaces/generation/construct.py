"""WorkspaceConstructor — project a workenv onto a workdir across recipes.

The single entry point of the generation submodule. It wraps the two
disk-writers — ``render`` (config-derived files: context, subagents, mcp,
permissions) and ``materialize_workspace`` (resource-backed bindings:
skills, documents, folders) — and fans them out over every engine recipe it
was handed, so callers stop hand-rolling the ``for engine in recipes`` loop.

It never imports the backend registry: recipes and the optional per-engine
``extra_items`` provider are injected by the caller. That keeps this module
free of the engines↔generation import cycle (``engines.backends`` already
imports ``generation.inject``).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

from agentbox.core.data.workenv import WorkspaceConfig
from agentbox.core.workspaces.generation.generator import render
from agentbox.core.workspaces.generation.materialize import (
    MaterializeOutcome,
    materialize_workspace,
)
from agentbox.core.data.workenv import Item, RenderedDir
from agentbox.core.data.workenv import Recipe

# (engine, config) -> extra native config items for that engine. Supplied by
# the caller because building them needs the backend registry.
ExtraItemsFn = Callable[[str, WorkspaceConfig], list[Item]]


class WorkspaceConstructor:
    """Generate + materialize a workenv across several engine recipes."""

    def __init__(
        self,
        recipes: Iterable[Recipe],
        *,
        extra_items: ExtraItemsFn | None = None,
    ) -> None:
        self._recipes = list(recipes)
        self._extra_items = extra_items

    @property
    def recipes(self) -> list[Recipe]:
        return list(self._recipes)

    def generate(
        self,
        target_dir: Path,
        config: WorkspaceConfig,
        *,
        system_prompt: str | None = None,
    ) -> list[RenderedDir]:
        """Render *config* to *target_dir* once per recipe. Engine-agnostic."""
        rendered: list[RenderedDir] = []
        for recipe in self._recipes:
            extra = self._extra_items(recipe.engine, config) if self._extra_items else []
            rendered.append(
                render(
                    target_dir,
                    config,
                    recipe,
                    system_prompt=system_prompt,
                    extra_items=extra,
                )
            )
        return rendered

    def materialize(
        self,
        workdir: Path,
        resolved_bindings: Iterable[dict],
        *,
        cache_root: Path | None = None,
    ) -> list[MaterializeOutcome]:
        """Materialize resource bindings; skills land per-recipe layout."""
        return materialize_workspace(
            workdir,
            resolved_bindings,
            recipes=self._recipes,
            cache_root=cache_root,
        )
