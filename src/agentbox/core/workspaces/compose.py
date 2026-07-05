"""WorkspaceComposer — produces a ``WorkspaceBlueprint`` from DB state.

Pure in-memory composition: reads managers, resolves agents/bindings/env-doc,
loads recipes, and returns the immutable blueprint.  No disk I/O, no network.
"""

from __future__ import annotations

import logging
from typing import cast

from agentbox.core.config import Settings
from agentbox.core.data.workenv import (
    EffectivePermissionsOverlay,
    Recipe,
    ResolvedBinding,
    ResolvedSubagent,
    WorkspaceBlueprint,
)
from agentbox.core.db import WorkspaceReadManager
from agentbox.core.engines.backends.recipe_loader import list_recipes, load_recipe

logger = logging.getLogger(__name__)


class WorkspaceComposer:
    """Assembles a ``WorkspaceBlueprint`` from workspace DB state.

    Callers (the ``Workspaces`` facade) inject the read manager once;
    ``compose()`` is the single entry point.
    """

    def __init__(self, workspace_read: WorkspaceReadManager) -> None:
        self._read = workspace_read

    def compose(
        self,
        workspace_id: str,
        settings: Settings,
    ) -> WorkspaceBlueprint:
        """Load workspace state and produce an immutable blueprint.

        Steps:
          1. Load workspace metadata.
          2. Resolve subagents (agent → profile → recipe).
          3. Resolve resource bindings.
          4. Load active env-doc body.
          5. Resolve runtime permissions overlay.
          6. Assemble and return the blueprint.
        """
        ws = self._read.get_workspace(workspace_id)
        if ws is None:
            raise ValueError(f"Workspace {workspace_id!r} not found")

        slug = ws.get("slug") or ws.get("id", workspace_id)
        workdir = settings.workspaces_root / slug
        agents = self._resolve_subagents(workspace_id)
        recipes = self._load_recipes(agents)
        bindings = self._resolve_bindings(workspace_id)
        env_doc_body = self._resolve_env_doc(workspace_id)
        permissions = self._resolve_permissions(workspace_id)

        return WorkspaceBlueprint(
            workspace_id=workspace_id,
            workdir=workdir,
            recipes=recipes,
            agents=agents,
            bindings=bindings,
            env_doc_body=env_doc_body,
            permissions=permissions,
            secrets_keys=(),
        )

    def _resolve_subagents(self, workspace_id: str) -> tuple[ResolvedSubagent, ...]:
        rows = self._read.list_subagents(workspace_id)
        return tuple(
            ResolvedSubagent(
                workspace_id=workspace_id,
                agent_id=r["agent_id"],
                alias=r["alias"],
                description=None,
                prompt_content="",
            )
            for r in rows
        )

    def _load_recipes(self, agents: tuple[ResolvedSubagent, ...]) -> tuple[Recipe, ...]:
        engine_names: set[str] = set()
        for a in agents:
            if a.agent_id:
                engine_names.add(a.agent_id)
        if not engine_names:
            names = list_recipes()
            return tuple(r for n in names if (r := load_recipe(n)) is not None)
        recipe_list: list[Recipe] = []
        for name in engine_names:
            recipe = load_recipe(name)
            if recipe is not None:
                recipe_list.append(recipe)
        if not recipe_list:
            names = list_recipes()
            recipe_list = [r for n in names if (r := load_recipe(n)) is not None]
        return tuple(recipe_list)

    def _resolve_bindings(self, workspace_id: str) -> tuple[ResolvedBinding, ...]:
        return ()

    def _resolve_env_doc(self, workspace_id: str) -> str | None:
        doc = self._read.get_active_env_doc(workspace_id)
        if doc is None:
            return None
        content = doc.get("content_json")
        if isinstance(content, dict):
            return content.get("body")
        return None

    def _resolve_permissions(self, workspace_id: str) -> EffectivePermissionsOverlay | None:
        row = self._read.get_runtime_permissions(workspace_id)
        if row is None:
            return None
        result: dict[str, object] = {}
        if row.get("allowed_builtin_tools") is not None:
            result["allowed_builtin_tools"] = row["allowed_builtin_tools"]
        if row.get("files") is not None:
            result["files"] = cast("list[dict]", row["files"])
        if row.get("max_tokens") is not None:
            result["max_tokens"] = row["max_tokens"]
        if row.get("allow_file_write") is not None:
            result["allow_file_write"] = bool(row["allow_file_write"])
        if row.get("allow_network") is not None:
            result["allow_network"] = bool(row["allow_network"])
        return cast("EffectivePermissionsOverlay | None", result if result else None)
