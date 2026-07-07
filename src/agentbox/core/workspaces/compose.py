"""WorkspaceComposer — produces a ``WorkspaceBlueprint`` from DB state.

Pure in-memory composition: reads everything through a single
``WorkspaceReadManager``, resolves subagents / bindings / env-doc /
permissions, builds the engine-agnostic ``WorkspaceConfig``, loads recipes,
and returns the immutable blueprint. No disk I/O, no network.
"""

from __future__ import annotations

import json
import logging

from agentbox.core.data.workenv import (
    AgentRef,
    EffectivePermissionsOverlay,
    McpRef,
    Permissions,
    Recipe,
    ResolvedBinding,
    ResolvedSubagent,
    ResourceRef,
    SourceMetadata,
    WorkspaceConfig,
    WorkspaceBlueprint,
)
from agentbox.core.db import WorkspaceReadManager
from agentbox.core.db.system.config import load_project_mcp_servers
from agentbox.core.engines.backends.recipe_loader import list_recipes, load_recipe

logger = logging.getLogger(__name__)

_EPHEMERAL = "<ephemeral>"


def _parse_source_metadata(raw: str | None) -> SourceMetadata | None:
    """Parse a version's JSON ``source_metadata`` into the typed shape."""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    out: SourceMetadata = {}
    filename = parsed.get("filename")
    if isinstance(filename, str):
        out["filename"] = filename
    host_path = parsed.get("host_path")
    if isinstance(host_path, str):
        out["host_path"] = host_path
    return out or None


class WorkspaceComposer:
    """Assembles a ``WorkspaceBlueprint`` from workspace DB state.

    The ``Workspaces`` facade injects the read manager + settings once;
    ``compose()`` is the single entry point.
    """

    def __init__(self, reads: WorkspaceReadManager) -> None:
        self._read = reads

    def compose(self, workspace_id: str) -> WorkspaceBlueprint:
        """Load workspace state and produce an immutable blueprint."""
        permissions = self._permissions(workspace_id)
        env_doc_body, env_doc_version_id = self._env_doc(workspace_id)
        return WorkspaceBlueprint(
            workspace_id=workspace_id,
            config=self._config(workspace_id, permissions),
            recipes=self._engines(),
            bindings=self._bindings(workspace_id),
            subagents=self._subagents(workspace_id),
            env_doc_body=env_doc_body,
            env_doc_version_id=env_doc_version_id,
            permissions=permissions,
            # ponytail: write_secrets is dead (no producer today); the blueprint
            # carries key NAMES only — wire a producer here when secrets return.
            secret_keys=(),
        )

    # ── engines ──────────────────────────────────────────────────────────

    def _engines(self) -> tuple[Recipe, ...]:
        # ponytail: load ALL installed recipes (current behaviour). Narrowing
        # to the workspace's actual engines (via agent runner profiles) is the
        # upgrade path if recipe load cost ever matters.
        return tuple(r for name in list_recipes() if (r := load_recipe(name)) is not None)

    # ── bindings ─────────────────────────────────────────────────────────

    def _bindings(self, workspace_id: str) -> tuple[ResolvedBinding, ...]:
        if not workspace_id or workspace_id == _EPHEMERAL:
            return ()
        out: list[ResolvedBinding] = []
        for b in self._read.list_file_bindings(workspace_id):
            resource = self._read.get_resource(b["resource_id"])
            if resource is None:
                logger.warning(
                    "compose: binding %s references missing resource %s — skipping",
                    b["id"],
                    b["resource_id"],
                )
                continue
            version_id = b["pinned_version_id"]
            if not version_id:
                active = self._read.get_active_resource_version(b["resource_id"])
                if active is None:
                    logger.warning(
                        "compose: resource %s has no active version — skipping binding %s",
                        resource["slug"],
                        b["id"],
                    )
                    continue
                version_id = active["id"]
            version = self._read.get_resource_version(version_id)
            if version is None:
                logger.warning(
                    "compose: version %s not found — skipping binding %s",
                    version_id,
                    b["id"],
                )
                continue
            out.append(
                ResolvedBinding(
                    binding_id=b["id"],
                    resource_id=b["resource_id"],
                    version_id=version_id,
                    content_hash=version["content_hash"],
                    type=resource["type"],
                    slug=resource["slug"],
                    display_name=resource["display_name"],
                    target_path=b["target_path"],
                    materialize_mode=b["materialize_mode"],
                    on_conflict=b["on_conflict"],
                    blobs=tuple(self._read.iter_blobs(version_id)),
                    source_metadata=_parse_source_metadata(version["source_metadata"]),
                )
            )
        return tuple(out)

    # ── subagents ────────────────────────────────────────────────────────

    def _subagents(self, workspace_id: str) -> tuple[ResolvedSubagent, ...]:
        if not workspace_id or workspace_id == _EPHEMERAL:
            return ()
        out: list[ResolvedSubagent] = []
        for r in self._read.list_subagents(workspace_id):
            agent_id = r["agent_id"]
            active = self._read.get_active_agent_version(agent_id)
            prompt = active["prompt_snapshot"] if active is not None else ""
            if not prompt:
                logger.warning(
                    "compose: subagent %s for workspace %s — agent %s has no active "
                    "prompt content; skipping",
                    r["alias"],
                    workspace_id,
                    agent_id,
                )
                continue
            agent_def = self._read.get_agent_def(agent_id)
            out.append(
                ResolvedSubagent(
                    workspace_id=workspace_id,
                    agent_id=agent_id,
                    alias=r["alias"],
                    description=agent_def.description if agent_def is not None else None,
                    prompt_content=prompt,
                )
            )
        return tuple(out)

    # ── env-doc ──────────────────────────────────────────────────────────

    def _env_doc(self, workspace_id: str) -> tuple[str | None, str | None]:
        if not workspace_id or workspace_id == _EPHEMERAL:
            return None, None
        doc = self._read.get_active_env_doc(workspace_id)
        if doc is None:
            return None, None
        content = doc["content_json"]  # already a parsed mapping on the row
        body = content.get("body") or content.get("content")
        body_str = body if isinstance(body, str) else (str(body) if body else None)
        return body_str, str(doc["id"])

    # ── permissions overlay ──────────────────────────────────────────────

    def _permissions(self, workspace_id: str) -> EffectivePermissionsOverlay | None:
        if not workspace_id or workspace_id == _EPHEMERAL:
            return None
        overlay = self._read.get_runtime_permissions(workspace_id)
        if overlay is None:
            return None
        result: EffectivePermissionsOverlay = {}
        tools = overlay["allowed_builtin_tools"]
        if tools is not None:
            result["allowed_builtin_tools"] = tools
        files = overlay["files"]
        if files is not None:
            result["files"] = files
        max_tokens = overlay["max_tokens"]
        if max_tokens is not None:
            result["max_tokens"] = max_tokens
        allow_file_write = overlay["allow_file_write"]
        if allow_file_write is not None:
            result["allow_file_write"] = bool(allow_file_write)
        allow_network = overlay["allow_network"]
        if allow_network is not None:
            result["allow_network"] = bool(allow_network)
        return result or None

    # ── engine-agnostic config (WorkspaceConfig) ───────────────────────────

    def _config(
        self, workspace_id: str, permissions: EffectivePermissionsOverlay | None
    ) -> WorkspaceConfig:
        agents: list[AgentRef] = []
        if self._read.get_agent_def(workspace_id) is not None:
            agents.append(AgentRef(id=workspace_id, role="main"))
        for sa in self._read.list_subagents(workspace_id):
            sub_agent_id = sa["agent_id"]
            active = self._read.get_active_agent_version(sub_agent_id)
            prompt = active["prompt_snapshot"] if active is not None else ""
            if not prompt:
                continue
            sub_def = self._read.get_agent_def(sub_agent_id)
            agents.append(
                AgentRef(
                    id=sa["alias"],
                    role="subagent",
                    description=(sub_def.description if sub_def is not None else "") or "",
                    prompt=prompt,
                )
            )

        resources = [
            ResourceRef(id=b["resource_id"])
            for b in self._read.list_file_bindings(workspace_id)
        ]

        project_servers = load_project_mcp_servers()
        server_overrides = {
            o["server_name"]: o for o in self._read.list_mcp_overrides(workspace_id)
        }
        tool_overrides = self._read.list_mcp_tool_overrides(workspace_id)
        mcp_servers: list[McpRef] = []
        for srv in project_servers:
            override = server_overrides.get(srv.name)
            if override is not None and override["enabled"] is False:
                continue
            disabled = [
                t["tool_name"]
                for t in tool_overrides
                if t["server_name"] == srv.name and not t["enabled"]
            ]
            mcp_servers.append(
                McpRef(
                    name=srv.name,
                    config={
                        k: v
                        for k, v in {
                            "url": srv.url,
                            "command": srv.command,
                            "transport": srv.transport,
                        }.items()
                        if v is not None
                    },
                    disabled_tools=disabled,
                )
            )

        env_doc_body, _ = self._env_doc(workspace_id)

        return WorkspaceConfig(
            name=workspace_id,
            # ponytail: workspace row exposes no description today (the old
            # loader read it via getattr on a dict row → always ""); keep "".
            description="",
            env_doc=env_doc_body,
            agents=agents,
            resources=resources,
            skills=[],
            mcp_servers=mcp_servers,
            permissions=Permissions(data=dict(permissions) if permissions else {}),
            env={},
        )
