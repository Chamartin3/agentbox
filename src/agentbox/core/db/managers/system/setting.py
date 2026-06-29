"""SettingManager — application settings key-value CRUD (composite PK)."""
from __future__ import annotations

import json as _json

from sqlalchemy import select as sa_select, delete as sa_delete
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.system.setting import Setting
from agentbox.core.data.manifests.workspaces import McpServerSpec

_PROJ_MCP_SERVERS = "project_mcp_servers"
_PROJ_SHARED_ASSETS = "project_shared_assets"


class SettingManager(Manager[Setting]):
    """Manager for the ``settings`` table (composite PK section+key).

    The generic ``get()`` / ``update()`` / ``delete()`` raise
    ``NotImplementedError`` for composite-PK tables. All operations
    use the custom methods below instead.
    """

    model = Setting

    # ------------------------------------------------------------------
    # Domain-specific operations (pure DB — no business logic)
    # ------------------------------------------------------------------

    def list_sections(self) -> list[str]:
        """Return the distinct section names that have at least one key set."""
        tbl = Setting.__table__
        with self._engine.connect() as conn:
            rows = conn.execute(
                sa_select(tbl.c.section).distinct()
            )
            return [r[0] for r in rows]

    def get_section(self, section: str) -> list[dict]:
        """Return all ``{key, value_json}`` rows in a section."""
        tbl = Setting.__table__
        with self._engine.connect() as conn:
            rows = conn.execute(
                sa_select(tbl).where(tbl.c.section == section)
            )
            return [
                {"key": r._mapping["key"], "value_json": r._mapping["value_json"]}
                for r in rows
            ]

    def get_settings_section(self, section: str) -> dict:
        """Return a section as ``{key: deserialised_value}``."""
        out: dict = {}
        for r in self.get_section(section):
            try:
                out[r["key"]] = _json.loads(r["value_json"])
            except (_json.JSONDecodeError, TypeError):
                out[r["key"]] = r["value_json"]
        return out

    def get_project_mcp_servers(self) -> list[McpServerSpec]:
        """Project-level MCP servers, parsed from the settings section."""
        out: list[McpServerSpec] = []
        for name, raw in self.get_settings_section(_PROJ_MCP_SERVERS).items():
            if not isinstance(raw, dict):
                continue
            data = {**raw, "name": raw.get("name") or name}
            try:
                out.append(McpServerSpec.model_validate(data))
            except Exception:
                continue
        return out

    def get_project_shared_assets(self) -> dict[str, str]:
        """Project shared-asset roots as ``{name: path}``."""
        section = self.get_settings_section(_PROJ_SHARED_ASSETS)
        return {k: str(v) for k, v in section.items() if isinstance(v, str)}

    def get_value(self, section: str, key: str) -> str | None:
        """Return the ``value_json`` string for one key, or None."""
        tbl = Setting.__table__
        with self._engine.connect() as conn:
            row = conn.execute(
                sa_select(tbl.c.value_json).where(
                    (tbl.c.section == section) & (tbl.c.key == key)
                )
            ).first()
        if row is None:
            return None
        return row[0]

    def upsert(
        self,
        section: str,
        key: str,
        value_json: str,
        updated_at: str,
        updated_by: str | None,
    ) -> None:
        """Insert or update a single setting row."""
        tbl = Setting.__table__
        stmt = sqlite_insert(tbl).values(
            section=section,
            key=key,
            value_json=value_json,
            updated_at=updated_at,
            updated_by=updated_by,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["section", "key"],
            set_={
                "value_json": value_json,
                "updated_at": updated_at,
                "updated_by": updated_by,
            },
        )
        with self._engine.begin() as conn:
            conn.execute(stmt)

    def delete_section_key(self, section: str, key: str) -> bool:
        """Delete a single key from a section. Returns True if deleted."""
        tbl = Setting.__table__
        with self._engine.begin() as conn:
            res = conn.execute(
                sa_delete(tbl).where(
                    (tbl.c.section == section) & (tbl.c.key == key)
                )
            )
            return res.rowcount > 0
