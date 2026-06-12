"""Workspace-scoped MCP overrides (Plan 05).

Adds an opt-in/opt-out overlay over manifest-declared MCP servers:

- Server-level enable/disable + per-server config overrides.
- Tool-level enable/disable within an enabled server.
- A workspace-default policy: ``allow_all_unless_disabled`` or
  ``deny_all_unless_enabled``.

The resolver function turns (manifest_servers, workspace_id) into the
filtered set the runner should see.
"""

from __future__ import annotations

import uuid

from sqlalchemy.engine import Engine

from agentbox.core.constants import McpPolicy
from agentbox.core.data.execution.snapshots import McpSnapshot
from agentbox.core.data.utils import now_iso
from agentbox.core.data.schema import (
    workspace_mcp_overrides,
    workspace_mcp_policies,
    workspace_mcp_tool_overrides,
)

def _validate_changelog(s: str) -> str:
    if not s or len(s.strip()) < 3:
        raise ValueError("changelog must be at least 3 characters")
    return s.strip()


def _shallow_merge(base: dict | None, overrides: dict | None) -> dict:
    out = dict(base or {})
    out.update(overrides or {})
    return out


class McpOverridesMixin:
    engine: Engine

    # --- policy ---

    def get_workspace_mcp_policy(self, workspace_id: str) -> McpPolicy:
        with self.engine.connect() as conn:
            row = conn.execute(
                workspace_mcp_policies.select().where(
                    workspace_mcp_policies.c.workspace_id == workspace_id
                )
            ).first()
            if not row:
                return McpPolicy.ALLOW_ALL_UNLESS_DISABLED
            return McpPolicy(row.default_policy)

    def set_workspace_mcp_policy(self, workspace_id: str, policy: str) -> McpPolicy:
        resolved = McpPolicy.coerce(policy, label="policy")
        with self.engine.begin() as conn:
            existing = conn.execute(
                workspace_mcp_policies.select().where(
                    workspace_mcp_policies.c.workspace_id == workspace_id
                )
            ).first()
            if existing:
                conn.execute(
                    workspace_mcp_policies.update()
                    .where(workspace_mcp_policies.c.workspace_id == workspace_id)
                    .values(default_policy=resolved)
                )
            else:
                conn.execute(
                    workspace_mcp_policies.insert().values(
                        workspace_id=workspace_id, default_policy=resolved
                    )
                )
        return resolved

    # --- server-level ---

    def list_workspace_mcp_server_overrides(self, workspace_id: str) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                workspace_mcp_overrides.select().where(
                    workspace_mcp_overrides.c.workspace_id == workspace_id
                )
            )
            return [dict(r._mapping) for r in rows]

    def set_workspace_mcp_server_override(
        self,
        workspace_id: str,
        server_name: str,
        *,
        enabled: bool,
        config_overrides: dict | None = None,
        changelog: str,
        actor: str | None = None,
    ) -> dict:
        changelog = _validate_changelog(changelog)
        now = now_iso()
        with self.engine.begin() as conn:
            existing = conn.execute(
                workspace_mcp_overrides.select().where(
                    (workspace_mcp_overrides.c.workspace_id == workspace_id)
                    & (workspace_mcp_overrides.c.server_name == server_name)
                )
            ).first()
            if existing:
                conn.execute(
                    workspace_mcp_overrides.update()
                    .where(workspace_mcp_overrides.c.id == existing.id)
                    .values(
                        enabled=1 if enabled else 0,
                        config_overrides=config_overrides,
                        changelog=changelog,
                        created_at=now,
                        created_by=actor,
                    )
                )
                row_id = existing.id
            else:
                row_id = uuid.uuid4().hex
                conn.execute(
                    workspace_mcp_overrides.insert().values(
                        id=row_id,
                        workspace_id=workspace_id,
                        server_name=server_name,
                        enabled=1 if enabled else 0,
                        config_overrides=config_overrides,
                        changelog=changelog,
                        created_at=now,
                        created_by=actor,
                    )
                )
        with self.engine.connect() as conn:
            row = conn.execute(
                workspace_mcp_overrides.select().where(
                    workspace_mcp_overrides.c.id == row_id
                )
            ).first()
        assert row is not None
        return dict(row._mapping)

    # --- tool-level ---

    def list_workspace_mcp_tool_overrides(self, workspace_id: str) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                workspace_mcp_tool_overrides.select().where(
                    workspace_mcp_tool_overrides.c.workspace_id == workspace_id
                )
            )
            return [dict(r._mapping) for r in rows]

    def set_workspace_mcp_tool_override(
        self,
        workspace_id: str,
        server_name: str,
        tool_name: str,
        *,
        enabled: bool,
        actor: str | None = None,
    ) -> dict:
        now = now_iso()
        with self.engine.begin() as conn:
            existing = conn.execute(
                workspace_mcp_tool_overrides.select().where(
                    (workspace_mcp_tool_overrides.c.workspace_id == workspace_id)
                    & (workspace_mcp_tool_overrides.c.server_name == server_name)
                    & (workspace_mcp_tool_overrides.c.tool_name == tool_name)
                )
            ).first()
            if existing:
                conn.execute(
                    workspace_mcp_tool_overrides.update()
                    .where(workspace_mcp_tool_overrides.c.id == existing.id)
                    .values(
                        enabled=1 if enabled else 0, created_at=now, created_by=actor
                    )
                )
                row_id = existing.id
            else:
                row_id = uuid.uuid4().hex
                conn.execute(
                    workspace_mcp_tool_overrides.insert().values(
                        id=row_id,
                        workspace_id=workspace_id,
                        server_name=server_name,
                        tool_name=tool_name,
                        enabled=1 if enabled else 0,
                        created_at=now,
                        created_by=actor,
                    )
                )
        with self.engine.connect() as conn:
            row = conn.execute(
                workspace_mcp_tool_overrides.select().where(
                    workspace_mcp_tool_overrides.c.id == row_id
                )
            ).first()
        assert row is not None
        return dict(row._mapping)

    # --- resolver ---

    def resolve_workspace_mcp(
        self,
        workspace_id: str,
        manifest_servers: list[dict],
        *,
        discovered_tools: dict[str, list[str]] | None = None,
    ) -> McpSnapshot:
        """Apply overrides to ``manifest_servers``.

        Each manifest entry is a dict with at least ``name`` and ``config``
        (whatever shape the runner expects). ``discovered_tools`` optionally
        maps server_name → tool names for tool-level filtering. Returns
        ``{"servers": [...], "policy": str}`` where each server has
        ``enabled``, ``config`` (merged), and ``disabled_tools``.
        """
        policy = self.get_workspace_mcp_policy(workspace_id)
        server_overrides = {
            o["server_name"]: o
            for o in self.list_workspace_mcp_server_overrides(workspace_id)
        }
        tool_overrides: dict[tuple[str, str], bool] = {}
        for t in self.list_workspace_mcp_tool_overrides(workspace_id):
            tool_overrides[(t["server_name"], t["tool_name"])] = bool(t["enabled"])

        manifest_by_name = {s["name"]: s for s in manifest_servers}
        # Union: every server visible in either manifest or overrides.
        all_names = list(manifest_by_name.keys())
        for n in server_overrides:
            if n not in manifest_by_name:
                all_names.append(n)

        out_servers = []
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
            if manifest_entry is not None:
                source = "override" if override else "default"
            else:
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
