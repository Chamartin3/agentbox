"""WorkspaceService — the workspace-domain public service object.

Stateful: the ``Database`` (managers) is resolved internally by ``Service``
from settings — never passed in. Methods take only their domain arguments,
never ``db`` or ``store``. Logic lives on the managers, this object owns
the rules: existence guards, timestamps, upsert branching, changelog
validation, cross-manager orchestration.
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from contextlib import contextmanager, suppress
from pathlib import Path
from collections.abc import Iterator
from typing import Any

from agentbox.core.config import Settings, load_settings
from agentbox.core.data.constants import McpPolicy
from agentbox.core.data import EnvDocPreviewResult, EnvDocRow
from agentbox.core.data.payload_types import (
    EffectivePermissions,
    PermissionFileEntry,
    EnvDocRenderEntry,
    GeneratedConfigsResult,
    GeneratedSkillsResult,
    McpDiscoveryRefreshResult,
    McpServerConfigView,
    McpToolGroup,
    PermissionsPatch,
    PermissionsSetResult,
    PermissionsView,
    ResolvedHostEnv,
    ResolvedMcpServer,
    ResolvedWorkspaceMcp,
    SkillContentResult,
    SkillsListResult,
    SubagentSpec,
    WorkspaceDeleteResult,
    WorkspaceFileRead,
    WorkspaceFileWrite,
    WorkspaceListItem,
    WorkspaceMcpToolsResult,
)
from agentbox.core.data.rows import (
    HostEnvProfileRow,
    WorkspaceMcpOverrideRow,
    WorkspaceMcpToolOverrideRow,
    WorkspaceRuntimePermissionRow,
    WorkspaceRow,
    WorkspaceSubagentRow,
    WorkspaceHostEnvGrantRow,
)
from agentbox.core.tools.catalog import CallableItem
from agentbox.core.workspaces.catalog import resolve_host_env_callables, resolve_workspace_callables
from agentbox.core.workspaces.mcp.catalog import resolve_mcp_callables
from agentbox.core.resources.skills import discover_skills, find_skill
from agentbox.core.service.base import Service
from agentbox.core.service.system.service import SystemService
from agentbox.core.workspaces.build import build_workspace_by_name, WorkspaceSyncResult
from agentbox.core.workspaces.generation.builders.from_db import load_workenv as _load_workenv_from_db
from agentbox.core.workspaces.generation.config import McpRef, WorkenvConfig
from agentbox.core.workspaces.generation.generator import render
from agentbox.core.data.workenv import RenderedFile
from agentbox.core.workspaces.generation.payload import RenderedDir
from agentbox.core.workspaces.generation.recipe import Recipe
from agentbox.core.engines.backends.recipe_loader import (
    list_recipes,
    load_recipe,
)
from agentbox.core.workspaces.construct import (
    native_extra_items,
    workspace_constructor,
)
from agentbox.core.workspaces.permissions import resolve_grants
from agentbox.core.workspaces.prep import render_env_doc as _render_env_doc

from agentbox.core.data.errors import WorkspaceExists, WorkspaceNotFound, WorkspacePathEscape

logger = logging.getLogger(__name__)

_FILE_HIDE_PREFIXES = (
    ".agentbox/",
    ".claude/",
    ".opencode/",
    "permissions/",
    "skills/",
)

_RENDERED_ARTIFACT_FILES = frozenset({"CLAUDE.md", "AGENTS.md"})

_READ_PREFIXES: frozenset[str] = frozenset(
    {"list_", "get_", "search_", "check_", "select_", "find_"}
)


# ── helpers ────────────────────────────────────────────────────────────


def _validate_changelog(s: str) -> str:
    if not s or len(s.strip()) < 3:
        raise ValueError("changelog must be at least 3 characters")
    return s.strip()


def _shallow_merge(base: McpServerConfigView | None, overrides: McpServerConfigView | None) -> McpServerConfigView:
    out: McpServerConfigView = {**(base or {}), **(overrides or {})}
    return out


def _bool_to_int(b: bool | None) -> int | None:
    if b is None:
        return None
    return 1 if b else 0


def _is_read_tool(tool: str) -> bool:
    return any(tool.startswith(rp) for rp in _READ_PREFIXES)


def is_user_file(rel_path: str) -> bool:
    if rel_path in _RENDERED_ARTIFACT_FILES:
        return False
    return not any(
        rel_path == p.rstrip("/") or rel_path.startswith(p) for p in _FILE_HIDE_PREFIXES
    )


# ── WorkspaceService ───────────────────────────────────────────────────


class WorkspaceService(Service):
    """Workspace lifecycle — policy over the db managers.

    Managers only touch tables; this object owns the rules: existence
    guards, timestamps, upsert branching, changelog validation,
    cross-manager orchestration.
    """

    def __init__(self) -> None:
        super().__init__()
        self._workspaces = self._db.workspaces
        self._env_doc_versions = self._db.workspace_env_doc_versions
        self._env_doc_pointers = self._db.workspace_env_docs
        self._mcp_policies = self._db.workspace_mcp_policies
        self._mcp_overrides = self._db.workspace_mcp_overrides
        self._mcp_tool_overrides = self._db.workspace_mcp_tool_overrides
        self._runtime_permissions = self._db.workspace_runtime_permissions
        self._host_env_grants = self._db.workspace_host_env_grants
        self._subagents = self._db.workspace_subagents
        self._discovery_cache = self._db.mcp_tool_discovery_cache
        self._subagents = self._db.workspace_subagents

    @property
    def _settings(self) -> Settings:
        return load_settings()

    def _get_resource_counts(self) -> dict[str, int]:
        try:
            return self._db.workspace_file_resource_bindings.count_by_workspace()
        except Exception:
            return {}

    # ═══════════════════════════════════════════════════════════════════
    # Workspace registry (from WorkspacesMixin + registry.py)
    # ═══════════════════════════════════════════════════════════════════

    def list_workspaces(
        self,
        *,
        settings: Settings | None = None,
    ) -> list[WorkspaceListItem]:
        _s = settings or self._settings
        registry = self._workspaces.list_all()
        ws_root = _s.workspaces_root
        disk_ids: set[str] = set()
        if ws_root.exists():
            disk_ids = {
                p.name
                for p in ws_root.iterdir()
                if p.is_dir() and not p.name.startswith(".")
            }

        resource_counts = self._get_resource_counts()

        result: list[WorkspaceListItem] = []
        for ws_row in registry:
            name = ws_row["name"]
            rel_path = ws_row.get("path")
            ws_path = _s.project_root / rel_path if rel_path else ws_root / name
            file_count = 0
            skill_count = 0
            if ws_path.exists():
                for p in ws_path.rglob("*"):
                    if p.is_file() and is_user_file(str(p.relative_to(ws_path))):
                        file_count += 1
                skill_count = len(discover_skills(ws_path))
            result.append(
                {
                    "name": name,
                    "path": str(ws_path),
                    "description": ws_row.get("description"),
                    "source": ws_row.get("source"),
                    "kind": "named",
                    "agents": [],
                    "agent_count": 0,
                    "file_count": file_count,
                    "skill_count": skill_count,
                    "resource_count": resource_counts.get(name, 0),
                    "exists": ws_path.exists(),
                    "on_disk": name in disk_ids,
                    "created_at": ws_row.get("created_at"),
                    "updated_at": ws_row.get("updated_at"),
                }
            )
        return result

    def get_workspace(self, name: str) -> WorkspaceRow | None:
        return self._workspaces.get_by_name(name)

    def require_workspace(self, name: str) -> WorkspaceRow:
        row = self._workspaces.get_by_name(name)
        if row is None:
            raise WorkspaceNotFound(name)
        return row

    def create_workspace(
        self,
        name: str,
        *,
        description: str | None = None,
        path: str | None = None,
        source: str = "db",
        actor: str | None = None,
    ) -> WorkspaceRow:
        if not name or not name.strip():
            raise ValueError("workspace name is required")
        if source not in ("manifest", "db"):
            raise ValueError(f"invalid source {source!r}")
        if self._workspaces.get_by_name(name) is not None:
            raise WorkspaceExists(name)
        return self._workspaces.insert(
            name, description=description, path=path, source=source, actor=actor
        )

    def upsert_workspace(
        self,
        name: str,
        *,
        description: str | None = None,
        path: str | None = None,
        source: str | None = None,
        actor: str | None = None,
    ) -> WorkspaceRow:
        return self._workspaces.upsert(
            name, description=description, path=path, source=source, actor=actor
        )

    def delete_workspace(
        self,
        name: str,
        *,
        settings: Settings | None = None,
        purge_disk: bool = False,
    ) -> WorkspaceDeleteResult:
        existing = self._workspaces.get_by_name(name)
        if existing is None:
            raise WorkspaceNotFound(name)
        counts = self._workspaces.delete_cascade(name)
        disk_removed = False
        if purge_disk:
            _s = settings or self._settings
            existing_path = existing.get("path")
            ws_path: Path
            if existing_path:
                ws_path = _s.project_root / existing_path
            else:
                ws_path = _s.workspaces_root / name
            if ws_path.exists() and ws_path.is_dir():
                shutil.rmtree(ws_path)
                disk_removed = True
        return {"deleted": name, "counts": counts, "disk_removed": disk_removed}

    def backfill_workspaces(self) -> int:
        return self._workspaces.backfill_from_satellites()

    def prune_phantoms(self, keep: set[str]) -> list[str]:
        return self._workspaces.prune_phantoms(keep)

    # ═══════════════════════════════════════════════════════════════════
    # Env docs (from EnvDocsMixin + env_doc.py)
    # ═══════════════════════════════════════════════════════════════════

    def get_active_env_doc(self, workspace_id: str) -> EnvDocRow | None:
        return self._env_doc_versions.get_active(workspace_id)

    def render_env_doc(self, workspace_id: str, workdir: Path) -> list[EnvDocRenderEntry]:
        """Render the active env doc's instruction files for a workspace."""
        return _render_env_doc(self._env_doc_versions, workspace_id, workdir)

    def list_env_doc_versions(self, workspace_id: str) -> list[EnvDocRow]:
        return self._env_doc_versions.list_for_workspace(workspace_id)

    def get_env_doc_version(self, version_id: str) -> EnvDocRow | None:
        return self._env_doc_versions.get_by_version_id(version_id)

    def save_env_doc(
        self,
        workspace_id: str,
        content: dict,
        *,
        changelog: str,
        publish: bool = True,
        actor: str | None = None,
    ) -> EnvDocRow:
        changelog = _validate_changelog(changelog)
        return self._env_doc_versions.save(
            workspace_id, content, changelog=changelog, publish=publish, actor=actor
        )

    def publish_env_doc(
        self,
        workspace_id: str,
        version_id: str,
    ) -> EnvDocRow:
        return self._env_doc_versions.publish(workspace_id, version_id)

    def rollback_env_doc(
        self,
        workspace_id: str,
        target_version_id: str,
        *,
        changelog: str,
        actor: str | None = None,
    ) -> EnvDocRow:
        changelog = _validate_changelog(changelog)
        target = self._env_doc_versions.get_by_version_id(target_version_id)
        if not target or target["workspace_id"] != workspace_id:
            raise ValueError(
                f"env doc version {target_version_id!r} not found for workspace"
            )
        return self._env_doc_versions.save(
            workspace_id,
            target["content_json"],
            changelog=changelog,
            publish=True,
            actor=actor,
        )

    def save_and_sync_env_doc(
        self,
        workspace_id: str,
        *,
        content: Any,
        reason: str = "edit",
        actor: str | None = None,
        settings: Settings | None = None,
    ) -> EnvDocRow:
        body = env_doc_body(content)
        result = self.save_env_doc(
            workspace_id, {"body": body}, changelog=reason, publish=True, actor=actor
        )
        _s = settings or self._settings
        try:
            build_workspace_by_name(
                self._workspaces,
                self._db.agent_defs,
                self._subagents,
                self._db.agent_versions,
                self._db.workspace_file_resource_bindings,
                self._db.resources,
                self._db.resource_versions,
                self._db.resource_blobs,
                self._mcp_overrides,
                self._mcp_tool_overrides,
                self._env_doc_versions,
                _s,
                workspace_id,
            )
        except Exception:
            logger.exception(
                "env_doc save: build_workspace_by_name failed for %s", workspace_id
            )
        return result

    def build_workspace(self, workspace_id: str) -> WorkspaceSyncResult | None:
        """Trigger a workspace build. Thin wrapper over ``build_workspace_by_name``.

        Returns ``None`` when the workspace has no resolvable workdir
        (unknown name, ephemeral, or path missing on disk).
        """
        return build_workspace_by_name(
            self._workspaces,
            self._db.agent_defs,
            self._subagents,
            self._db.agent_versions,
            self._db.workspace_file_resource_bindings,
            self._db.resources,
            self._db.resource_versions,
            self._db.resource_blobs,
            self._mcp_overrides,
            self._mcp_tool_overrides,
            self._env_doc_versions,
            self._settings,
            workspace_id,
        )

    # ═══════════════════════════════════════════════════════════════════
    # MCP policy + overrides (from McpOverridesMixin + mcp.py)
    # ═══════════════════════════════════════════════════════════════════

    def get_mcp_policy(self, workspace_id: str) -> McpPolicy:
        return self._mcp_policies.get_policy(workspace_id)

    def set_mcp_policy(self, workspace_id: str, policy: str) -> McpPolicy:
        resolved = McpPolicy.coerce(policy, label="policy")
        return self._mcp_policies.set_policy(workspace_id, resolved)

    def list_mcp_server_overrides(self, workspace_id: str) -> list[WorkspaceMcpOverrideRow]:
        return self._mcp_overrides.list_for_workspace(workspace_id)

    def set_mcp_server_override(
        self,
        workspace_id: str,
        server_name: str,
        *,
        enabled: bool,
        config_overrides: dict | None = None,
        changelog: str,
        actor: str | None = None,
    ) -> WorkspaceMcpOverrideRow:
        changelog = _validate_changelog(changelog)
        return self._mcp_overrides.set_override(
            workspace_id,
            server_name,
            enabled=enabled,
            config_overrides=config_overrides,
            changelog=changelog,
            actor=actor,
        )

    def list_mcp_tool_overrides(self, workspace_id: str) -> list[WorkspaceMcpToolOverrideRow]:
        return self._mcp_tool_overrides.list_for_workspace(workspace_id)

    def set_mcp_tool_override(
        self,
        workspace_id: str,
        server_name: str,
        tool_name: str,
        *,
        enabled: bool,
        actor: str | None = None,
    ) -> WorkspaceMcpToolOverrideRow:
        return self._mcp_tool_overrides.set_override(
            workspace_id, server_name, tool_name, enabled=enabled, actor=actor
        )

    def resolve_workspace_mcp(
        self,
        workspace_id: str,
        manifest_servers: list[dict] | None = None,
        *,
        discovered_tools: dict[str, list[str]] | None = None,
        settings: Settings | None = None,
    ) -> ResolvedWorkspaceMcp:
        if manifest_servers is None:
            _s = settings or self._settings
            servers = SystemService().get_project_mcp_servers()
            manifest_servers = [
                {"name": s.name, "config": s.model_dump(exclude={"name"})}
                for s in servers
            ] if servers else []

        policy = self._mcp_policies.get_policy(workspace_id)
        server_overrides = {
            o["server_name"]: o
            for o in self._mcp_overrides.list_for_workspace(workspace_id)
        }
        tool_overrides: dict[tuple[str, str], bool] = {}
        for t in self._mcp_tool_overrides.list_for_workspace(workspace_id):
            tool_overrides[(t["server_name"], t["tool_name"])] = bool(t["enabled"])

        manifest_by_name = {s["name"]: s for s in manifest_servers}
        all_names = list(manifest_by_name.keys())
        for n in server_overrides:
            if n not in manifest_by_name:
                all_names.append(n)

        out_servers: list[ResolvedMcpServer] = []
        for name in all_names:
            manifest_entry = manifest_by_name.get(name)
            override = server_overrides.get(name)
            if override is not None:
                enabled = bool(override["enabled"])
            else:
                enabled = policy == "allow_all_unless_disabled"
            base_cfg = manifest_entry.get("config") if manifest_entry else None
            cfg = _shallow_merge(base_cfg, (override or {}).get("config_overrides"))
            disabled_tools: list[str] = []
            if enabled and discovered_tools:
                for tool in discovered_tools.get(name, []):
                    flag = tool_overrides.get((name, tool))
                    if flag is False:
                        disabled_tools.append(tool)
            source = "override" if override else "default"
            if manifest_entry is None:
                source = "override_only"
            out_servers.append(
                {
                    "name": name,
                    "enabled": enabled,
                    "config": cfg,
                    "disabled_tools": disabled_tools,
                    "source": source,
                }
            )
        return {"servers": out_servers, "policy": policy}

    def refresh_mcp_discovery(self, workspace_id: str) -> McpDiscoveryRefreshResult:
        resolved = self.resolve_workspace_mcp(workspace_id)
        removed = 0
        for s in resolved.get("servers", []):
            removed += self._discovery_cache.invalidate_server_cache(s["name"])
        return {"invalidated": removed}

    # ═══════════════════════════════════════════════════════════════════
    # MCP discovery cache (from McpDiscoveryMixin)
    # ═══════════════════════════════════════════════════════════════════

    def get_cached_tools(
        self,
        server_name: str,
        config_hash: str,
        *,
        ttl_seconds: int | None = None,
    ) -> list[str] | None:
        return self._discovery_cache.get_cached_tools(
            server_name, config_hash, ttl_seconds=ttl_seconds
        )

    def cache_tools(
        self,
        server_name: str,
        config_hash: str,
        tools: list[str],
    ) -> None:
        self._discovery_cache.cache_tools(server_name, config_hash, tools)

    def invalidate_server_cache(self, server_name: str) -> int:
        return self._discovery_cache.invalidate_server_cache(server_name)

    # ═══════════════════════════════════════════════════════════════════
    # Runtime permissions (from RuntimePermissionsMixin + permissions.py)
    # ═══════════════════════════════════════════════════════════════════

    def get_runtime_permissions(self, workspace_id: str) -> WorkspaceRuntimePermissionRow | None:
        return self._runtime_permissions.get_for_workspace(workspace_id)

    def set_runtime_permissions(
        self,
        workspace_id: str,
        *,
        allowed_builtin_tools: list[str] | None = None,
        files: list[PermissionFileEntry] | None = None,
        max_tokens: int | None = None,
        allow_file_write: bool | None = None,
        allow_network: bool | None = None,
        actor: str | None = None,
    ) -> WorkspaceRuntimePermissionRow:
        return self._runtime_permissions.set_for_workspace(
            workspace_id,
            allowed_builtin_tools=allowed_builtin_tools,
            files=files,
            max_tokens=max_tokens,
            allow_file_write=allow_file_write,
            allow_network=allow_network,
            actor=actor,
        )

    # ═══════════════════════════════════════════════════════════════════
    # Host env (from HostEnvMixin)
    # ═══════════════════════════════════════════════════════════════════

    def list_host_env_profiles(self) -> list[HostEnvProfileRow]:
        return self._host_env_grants.list_profiles()

    def get_host_env_profile(self, profile_id: str) -> HostEnvProfileRow | None:
        return self._host_env_grants.get_profile(profile_id)

    def upsert_host_env_profile(
        self,
        *,
        name: str,
        grants: dict,
        description: str | None = None,
        actor: str | None = None,
        profile_id: str | None = None,
    ) -> HostEnvProfileRow:
        return self._host_env_grants.upsert_profile(
            name=name,
            grants=grants,
            description=description,
            actor=actor,
            profile_id=profile_id,
        )

    def delete_host_env_profile(self, profile_id: str) -> None:
        self._host_env_grants.delete_profile(profile_id)

    def get_workspace_host_env(self, workspace_id: str) -> WorkspaceHostEnvGrantRow | None:
        return self._host_env_grants.get_grant(workspace_id)

    def set_workspace_host_env(
        self,
        workspace_id: str,
        *,
        profile_id: str | None,
        overrides: dict | None,
        changelog: str,
        actor: str | None = None,
    ) -> WorkspaceHostEnvGrantRow:
        changelog = _validate_changelog(changelog)
        return self._host_env_grants.set_grant(
            workspace_id,
            profile_id=profile_id,
            overrides=overrides,
            changelog=changelog,
            actor=actor,
        )

    def resolve_workspace_host_env(self, workspace_id: str) -> ResolvedHostEnv:
        row = self._host_env_grants.get_grant(workspace_id)
        if not row:
            return {"grants": resolve_grants(None, None), "profile_id": None}
        profile_id = row.get("profile_id")
        profile = (
            self._host_env_grants.get_profile(profile_id)
            if profile_id is not None
            else None
        )
        grants = resolve_grants(
            profile["grants"] if profile else None, row.get("overrides")
        )
        return {
            "grants": grants,
            "profile_id": row.get("profile_id"),
            "overrides": row.get("overrides"),
        }

    # ═══════════════════════════════════════════════════════════════════
    # Callable catalog (host-env + MCP + resources)
    # ═══════════════════════════════════════════════════════════════════

    def installed_callables(
        self,
        workspace_id: str,
        *,
        mcp_registry: Any = None,
    ) -> list[CallableItem]:
        """Return every callable item (MCP, host-env, resource) installed in *workspace_id*."""
        return resolve_workspace_callables(
            workspace_id,
            self._host_env_grants,
            self._db.workspace_file_resource_bindings,
            self._mcp_policies,
            self._mcp_overrides,
            self._mcp_tool_overrides,
            mcp_registry,
        )

    def mcp_callables(
        self,
        workspace_id: str,
        mcp_registry: Any,
    ) -> list[CallableItem]:
        """Return MCP-source CallableItems for *workspace_id*."""
        return resolve_mcp_callables(
            workspace_id,
            self._mcp_policies,
            self._mcp_overrides,
            self._mcp_tool_overrides,
            mcp_registry,
        )

    def host_env_callables(self, workspace_id: str) -> list[CallableItem]:
        """Return host-env CallableItems for *workspace_id*."""
        return resolve_host_env_callables(workspace_id, self._host_env_grants)

    # ═══════════════════════════════════════════════════════════════════
    # Subagent bindings (from bindings.py)
    # ═══════════════════════════════════════════════════════════════════

    def list_subagents(self, workspace_id: str) -> list[WorkspaceSubagentRow]:
        return self._subagents.list_for_workspace(workspace_id)

    def replace_subagents(
        self,
        workspace_id: str,
        subagents: list[SubagentSpec],
        *,
        actor: str | None = None,
    ) -> list[WorkspaceSubagentRow]:
        return self._subagents.replace_for_workspace(
            workspace_id, subagents, actor=actor
        )

    # ═══════════════════════════════════════════════════════════════════
    # Workspace path resolution (from files.py)
    # ═══════════════════════════════════════════════════════════════════

    def resolve_workspace_path(
        self,
        name: str,
        *,
        settings: Settings | None = None,
    ) -> tuple[Path, Path]:
        _s = settings or self._settings
        row = self._workspaces.get_by_name(name)
        if row is None:
            raise WorkspaceNotFound(name)
        rel_path = row.get("path")
        ws_path = (
            _s.project_root / rel_path
            if rel_path
            else _s.workspaces_root / name
        )
        return ws_path, _s.project_root

    def _safe_resolve(self, ws_path: Path, rel: str) -> Path:
        target = (ws_path / rel).resolve()
        if not str(target).startswith(str(ws_path.resolve())):
            raise WorkspacePathEscape(rel)
        return target

    def read_workspace_file(
        self,
        name: str,
        path: str,
        *,
        settings: Settings | None = None,
    ) -> WorkspaceFileRead | None:
        ws_path, _ = self.resolve_workspace_path(name, settings=settings)
        target = self._safe_resolve(ws_path, path)
        if not target.is_file():
            return None
        return {"path": path, "content": target.read_text(encoding="utf-8")}

    def write_workspace_file(
        self,
        name: str,
        path: str,
        content: str,
        *,
        settings: Settings | None = None,
    ) -> WorkspaceFileWrite:
        ws_path, _ = self.resolve_workspace_path(name, settings=settings)
        target = self._safe_resolve(ws_path, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {"path": path, "bytes": len(content)}

    # ═══════════════════════════════════════════════════════════════════
    # Config generation (from configs.py)
    # ═══════════════════════════════════════════════════════════════════

    def _project_mcp_refs(
        self,
        servers: list[dict] | None = None,
    ) -> list[McpRef]:
        if servers is not None:
            specs = servers
        else:
            specs = SystemService().get_project_mcp_servers()
        refs: list[McpRef] = []
        for s in specs:
            name = s["name"] if isinstance(s, dict) else s.name
            if isinstance(s, dict):
                cfg = {k: v for k, v in s.items() if k != "name"}
            else:
                cfg = {
                    k: v
                    for k, v in {
                        "url": s.url,
                        "command": s.command,
                        "transport": str(s.transport) if s.transport else None,
                    }.items()
                    if v is not None
                }
            refs.append(McpRef(name=name, config=cfg))
        return refs

    @contextmanager
    def launch_runner_configs(
        self,
        workspace_path: Path,
        *,
        servers: list[dict] | None = None,
        keep: bool = False,
    ) -> Iterator[Path]:
        """Place native runner config in *workspace_path* for interactive launch.

        Context manager; yields workspace_path. Renders into temp dir first,
        copies only files that don't already exist, then removes on exit
        (unless *keep*). Never overwrites or deletes a user file.
        """
        config = WorkenvConfig(
            name="project", mcp_servers=self._project_mcp_refs(servers)
        )
        created: list[Path] = []
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            rels: set[str] = set()
            for rendered in workspace_constructor().generate(tmp_dir, config):
                for p in rendered.written_paths:
                    rels.add(str(p.relative_to(tmp_dir)))
            for rel in rels:
                dst = workspace_path / rel
                if dst.exists():
                    continue
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(tmp_dir / rel, dst)
                created.append(dst)
        try:
            yield workspace_path
        finally:
            if not keep:
                for p in created:
                    with suppress(OSError):
                        p.unlink()

    def _generate_into(
        self,
        workspace_path: Path,
        workspace_id: str,
    ) -> dict[str, str]:
        perms = self.load_effective_permissions(workspace_id)
        config = _load_workenv_from_db(
            self._workspaces,
            self._db.agent_defs,
            self._subagents,
            self._db.agent_versions,
            self._db.workspace_file_resource_bindings,
            self._mcp_overrides,
            self._mcp_tool_overrides,
            self._env_doc_versions,
            workspace_id,
            settings=self._settings,
            permissions=perms,
        )
        paths: dict[str, str] = {}
        for result in workspace_constructor().generate(workspace_path, config):
            for p in result.written_paths:
                try:
                    key = str(p.relative_to(workspace_path))
                except ValueError:
                    key = str(p)
                paths[key] = str(p)
        return paths

    def generate_configs(
        self,
        name: str,
        *,
        settings: Settings | None = None,
    ) -> GeneratedConfigsResult:
        ws_path, _ = self.resolve_workspace_path(name, settings=settings)
        paths = self._generate_into(ws_path, name)
        return {"workspace": str(ws_path), "generated": paths}

    def render_workenv(
        self,
        dir_path: Path,
        *,
        config: WorkenvConfig,
        recipe: Recipe,
    ) -> RenderedDir:
        """Render a WorkenvConfig to disk against a Recipe.

        Dispatches to the backend's ``build_workspace_items`` for
        engine-specific files and passes them as *extra_items*.
        """
        extra = native_extra_items(recipe.engine, config)
        return render(dir_path, config=config, recipe=recipe, extra_items=extra)

    def preview_workenv(
        self,
        *,
        config: WorkenvConfig,
        recipe: Recipe,
    ) -> list[RenderedFile]:
        """Render a WorkenvConfig to a throwaway dir and return the file contents."""
        with tempfile.TemporaryDirectory() as td:
            dir_path = Path(td)
            result = self.render_workenv(dir_path, config=config, recipe=recipe)
            return [
                RenderedFile(p.relative_to(dir_path), p.read_text(encoding="utf-8"))
                for p in result.written_paths
            ]

    def list_recipe_engines(self) -> list[str]:
        """List available recipe engine names (backends with a recipe.yaml)."""
        return list_recipes()

    def load_workenv_recipe(self, engine: str) -> Recipe:
        """Load the recipe for *engine*. Raises ``FileNotFoundError`` if absent."""
        return load_recipe(engine)

    def load_workenv(
        self,
        workspace_id: str,
        *,
        settings: Settings | None = None,
        permissions: EffectivePermissions | None = None,
    ) -> WorkenvConfig:
        """Load a ``WorkenvConfig`` for *workspace_id* from the DB."""
        return _load_workenv_from_db(
            self._workspaces,
            self._db.agent_defs,
            self._subagents,
            self._db.agent_versions,
            self._db.workspace_file_resource_bindings,
            self._mcp_overrides,
            self._mcp_tool_overrides,
            self._env_doc_versions,
            workspace_id,
            settings=settings or self._settings,
            permissions=permissions,
        )

    # ═══════════════════════════════════════════════════════════════════
    # Skill discovery (from skills.py)
    # ═══════════════════════════════════════════════════════════════════

    def _generate_skills_dir(
        self, skills: list, ws_path: Path, subdir: str
    ) -> Path:
        out_dir = ws_path / subdir / "skills"
        if out_dir.exists():
            shutil.rmtree(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        for skill in skills:
            skill_dir = out_dir / skill.name
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text(skill.content, encoding="utf-8")
        return out_dir

    def generate_skills(
        self,
        name: str,
        *,
        settings: Settings | None = None,
    ) -> GeneratedSkillsResult:
        ws_path, _ = self.resolve_workspace_path(name, settings=settings)
        skills = discover_skills(ws_path)
        claude_dir = self._generate_skills_dir(skills, ws_path, ".claude")
        opencode_dir = self._generate_skills_dir(skills, ws_path, ".opencode")
        return {
            "workspace": name,
            "skills_count": len(skills),
            "generated": {
                "claude_skills": str(claude_dir),
                "opencode_skills": str(opencode_dir),
            },
        }

    def list_skills(
        self,
        name: str,
        *,
        settings: Settings | None = None,
    ) -> SkillsListResult:
        ws_path, _ = self.resolve_workspace_path(name, settings=settings)
        skills = discover_skills(ws_path)
        return {
            "workspace": name,
            "workspace_path": str(ws_path),
            "skills": [
                {
                    "name": s.name,
                    "path": str(s.path.relative_to(ws_path)),
                    "size": len(s.content.encode("utf-8")),
                }
                for s in skills
            ],
        }

    def get_skill_content(
        self,
        name: str,
        skill_name: str,
        *,
        settings: Settings | None = None,
    ) -> SkillContentResult | None:
        ws_path, _ = self.resolve_workspace_path(name, settings=settings)
        skill_md = find_skill(ws_path, skill_name)
        if skill_md is None:
            return None
        return {
            "workspace": name,
            "skill": skill_name,
            "path": str(skill_md.relative_to(ws_path)),
            "content": skill_md.read_text(encoding="utf-8"),
        }

    # ═══════════════════════════════════════════════════════════════════
    # Effective permissions (from permissions.py)
    # ═══════════════════════════════════════════════════════════════════

    def _load_tool_manifest(self) -> dict[str, list[str]]:
        manifest_path = (
            self._settings.project_root / "bin" / "_generated" / "tool_manifest.json"
        )
        if not manifest_path.is_file():
            return {}
        with open(manifest_path) as f:
            return json.load(f)

    def _derive_allowed_tools(self, workspace_id: str) -> list[str]:
        tool_manifest = self._load_tool_manifest()
        if not tool_manifest:
            return []
        servers = SystemService().get_project_mcp_servers()
        mcp_server_name = servers[0].name if servers else "mcp"
        claude_prefix = f"mcp__{mcp_server_name}__"
        discovered = {
            mcp_server_name: [t for tools in tool_manifest.values() for t in tools]
        }
        resolved = self.resolve_workspace_mcp(
            workspace_id,
            [{"name": mcp_server_name, "config": {}}],
            discovered_tools=discovered,
        )
        out: list[str] = []
        for srv in resolved.get("servers", []):
            if not srv.get("enabled"):
                continue
            disabled = set(srv.get("disabled_tools") or [])
            for tool in discovered.get(srv["name"], []):
                if tool in disabled:
                    continue
                out.append(f"{claude_prefix}{tool}")
        return out

    def _apply_allowed_tools(
        self,
        workspace_id: str,
        allowed_tools: list[str],
    ) -> None:
        tool_manifest = self._load_tool_manifest()
        if not tool_manifest:
            return
        servers = SystemService().get_project_mcp_servers()
        mcp_server_name = servers[0].name if servers else "mcp"
        claude_prefix = f"mcp__{mcp_server_name}__"
        allowed = set(allowed_tools)
        for tools in tool_manifest.values():
            for tool in tools:
                prefixed = f"{claude_prefix}{tool}"
                enabled = prefixed in allowed
                self._mcp_tool_overrides.set_override(
                    workspace_id, mcp_server_name, tool, enabled=enabled
                )

    def load_effective_permissions(
        self,
        workspace_id: str,
    ) -> EffectivePermissions:
        perms: EffectivePermissions = {
            "allowed_tools": [],
            "allowed_builtin_tools": [],
            "files": [],
            "max_tokens": None,
            "allow_file_write": True,
            "allow_network": True,
        }
        if not workspace_id:
            return perms

        overlay = self._runtime_permissions.get_for_workspace(workspace_id)
        if overlay:
            builtin_tools = overlay["allowed_builtin_tools"]
            if builtin_tools is not None:
                perms["allowed_builtin_tools"] = builtin_tools
            file_entries = overlay["files"]
            if file_entries is not None:
                perms["files"] = file_entries
            if overlay.get("max_tokens") is not None:
                perms["max_tokens"] = overlay["max_tokens"]
            if overlay.get("allow_file_write") is not None:
                perms["allow_file_write"] = bool(overlay["allow_file_write"])
            if overlay.get("allow_network") is not None:
                perms["allow_network"] = bool(overlay["allow_network"])

        perms["allowed_tools"] = self._derive_allowed_tools(workspace_id)
        return perms

    def get_permissions(
        self,
        name: str,
    ) -> PermissionsView:
        ws_path, _ = self.resolve_workspace_path(name)
        permissions = self.load_effective_permissions(name)
        return {
            "workspace": name,
            "path": str(ws_path / "permissions" / "capabilities.json"),
            "permissions": permissions,
        }

    def set_permissions(
        self,
        name: str,
        permissions: PermissionsPatch,
        *,
        settings: Settings | None = None,
        sync_cb: Any = None,
    ) -> PermissionsSetResult:
        _s = settings or self._settings
        ws_path, _ = self.resolve_workspace_path(name, settings=_s)

        self._runtime_permissions.set_for_workspace(
            name,
            allowed_builtin_tools=permissions.get("allowed_builtin_tools"),
            files=permissions.get("files"),
            max_tokens=permissions.get("max_tokens"),
            allow_file_write=permissions.get("allow_file_write"),
            allow_network=permissions.get("allow_network"),
        )
        if "allowed_tools" in permissions and permissions["allowed_tools"] is not None:
            self._apply_allowed_tools(name, list(permissions["allowed_tools"]))

        effective = self.load_effective_permissions(name)
        _write_capabilities_artifact(ws_path, effective)

        config_result = self.generate_configs(name, settings=_s)

        if sync_cb is not None:
            try:
                sync_cb(self._settings, name)
            except Exception:
                pass

        return {
            "workspace": name,
            "path": str(ws_path / "permissions" / "capabilities.json"),
            "permissions": effective,
            "regenerated": config_result.get("generated", {}),
        }

    def get_workspace_mcp_tools(
        self,
        name: str,
    ) -> WorkspaceMcpToolsResult:
        servers = SystemService().get_project_mcp_servers()
        mcp_server_name = servers[0].name if servers else "mcp"
        claude_prefix = f"mcp__{mcp_server_name}__"
        opencode_prefix = f"{mcp_server_name}_"

        tool_manifest = self._load_tool_manifest()
        groups: list[McpToolGroup] = []
        for group_name, tools in tool_manifest.items():
            claude_tools = [f"{claude_prefix}{t}" for t in tools]
            opencode_tools = [f"{opencode_prefix}{t}" for t in tools]
            groups.append(
                {
                    "name": group_name,
                    "tools": tools,
                    "claude_tools": claude_tools,
                    "opencode_tools": opencode_tools,
                    "tool_count": len(tools),
                    "kind": "read" if all(_is_read_tool(t) for t in tools) else "mixed",
                }
            )

        builtin_tools = [
            "AskUserQuestion",
            "Task",
            "TodoRead",
            "TodoWrite",
            "WebFetch",
            "WebSearch",
        ]

        ws_path, _ = self.resolve_workspace_path(name)
        permissions = self.load_effective_permissions(name)
        allowed = set(permissions.get("allowed_tools", []))
        for g in groups:
            g["active"] = any(t in allowed for t in g["claude_tools"])
            g["fully_active"] = all(t in allowed for t in g["claude_tools"])

        return {
            "workspace": name,
            "mcp_server_name": mcp_server_name,
            "claude_prefix": claude_prefix,
            "opencode_prefix": opencode_prefix,
            "groups": groups,
            "builtin_tools": builtin_tools,
            "total_groups": len(groups),
            "total_tools": sum(g["tool_count"] for g in groups),
        }

    # -------------------------------------------------------------------
    # Subagents
    # -------------------------------------------------------------------

    def list_workspace_subagents_raw(self, workspace_id: str) -> list[WorkspaceSubagentRow]:
        """Return raw subagent rows for a workspace."""
        return self._subagents.list_for_workspace(workspace_id)

    def replace_workspace_subagents(
        self,
        workspace_id: str,
        subagents: list[SubagentSpec],
        *,
        actor: str | None = None,
    ) -> list[WorkspaceSubagentRow]:
        """Atomically replace workspace subagents and return rows."""
        return self._subagents.replace_for_workspace(workspace_id, subagents, actor=actor)


# ── helpers ────────────────────────────────────────────────────────────


def _write_capabilities_artifact(ws_path: Path, permissions: EffectivePermissions) -> None:
    perm_dir = ws_path / "permissions"
    perm_dir.mkdir(parents=True, exist_ok=True)
    perm_file = perm_dir / "capabilities.json"
    perm_file.write_text(
        json.dumps(permissions, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def env_doc_body(content: Any) -> str:
    """Extract the markdown body from a raw string or a ``{"body": ...}`` dict."""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        body = content.get("body") or content.get("content") or ""
        return body if isinstance(body, str) else str(body)
    return ""


def render_env_doc_preview(content: Any) -> EnvDocPreviewResult:
    """Preview the instruction files. Identical body for every engine."""
    body = env_doc_body(content)
    return {"claude_md": body, "agents_md": body}


def save_and_sync_env_doc(
    workspace_id: str,
    *,
    content: Any,
    reason: str = "edit",
    actor: str | None = None,
) -> EnvDocRow:
    """Persist env-doc as live version, then sync CLAUDE.md/AGENTS.md on disk."""
    return WorkspaceService().save_and_sync_env_doc(
        workspace_id, content=content, reason=reason, actor=actor
    )
