"""Project-level configuration backed by the ``settings`` table.

Holds project-wide config that used to live in ``agentbox.toml``:

- ``project_mcp_servers`` — one key per MCP server, value is the
  serialized ``McpServerSpec``.
- ``project_shared_assets`` — one key per shared-asset root, value is
  the project-relative path.
- ``project_runtime`` — scalar config: ``backend_preference`` (list),
  ``tool_manifest_path`` (str), ``project_name`` (str).

The mixin is composed into ``SessionStore``; callers use the typed
accessors here instead of touching ``SettingsMixin`` directly.
"""

from __future__ import annotations

from sqlalchemy.engine import Engine

from agentbox.core.data.workspaces.manifest import McpServerSpec
from agentbox.core.data.system.settings import SettingsMixin

PROJECT_MCP_SERVERS = "project_mcp_servers"
PROJECT_SHARED_ASSETS = "project_shared_assets"
PROJECT_RUNTIME = "project_runtime"


class ProjectConfigMixin(SettingsMixin):
    """Typed wrappers over ``SettingsMixin`` for project-level config.

    Requires ``SettingsMixin`` (``get_setting``, ``set_setting``,
    ``get_settings_section``, ``update_settings_section``) in the MRO.
    """

    engine: Engine

    # ----- MCP servers --------------------------------------------------

    def get_project_mcp_servers(self) -> list[McpServerSpec]:
        section = self.get_settings_section(PROJECT_MCP_SERVERS)
        out: list[McpServerSpec] = []
        for name, raw in section.items():
            if not isinstance(raw, dict):
                continue
            data = {**raw, "name": raw.get("name") or name}
            try:
                out.append(McpServerSpec.model_validate(data))
            except Exception:
                continue
        return out

    def set_project_mcp_server(
        self,
        spec: McpServerSpec,
        *,
        author: str | None = None,
    ) -> None:
        self.set_setting(
            PROJECT_MCP_SERVERS,
            spec.name,
            spec.model_dump(mode="json"),
            author=author,
        )

    def delete_project_mcp_server(self, name: str) -> None:
        from agentbox.core.data.schema import settings as settings_table

        with self.engine.begin() as conn:
            conn.execute(
                settings_table.delete().where(
                    (settings_table.c.section == PROJECT_MCP_SERVERS)
                    & (settings_table.c.key == name)
                )
            )

    # ----- shared assets ------------------------------------------------

    def get_project_shared_assets(self) -> dict[str, str]:
        section = self.get_settings_section(PROJECT_SHARED_ASSETS)
        return {k: str(v) for k, v in section.items() if isinstance(v, str)}

    def set_project_shared_asset(
        self, name: str, path: str, *, author: str | None = None
    ) -> None:
        self.set_setting(PROJECT_SHARED_ASSETS, name, path, author=author)

    def delete_project_shared_asset(self, name: str) -> None:
        from agentbox.core.data.schema import settings as settings_table

        with self.engine.begin() as conn:
            conn.execute(
                settings_table.delete().where(
                    (settings_table.c.section == PROJECT_SHARED_ASSETS)
                    & (settings_table.c.key == name)
                )
            )

    # ----- runtime scalars ----------------------------------------------

    def get_backend_preference(self) -> list[str]:
        value = self.get_setting(PROJECT_RUNTIME, "backend_preference", default=[])
        if isinstance(value, list):
            return [str(v) for v in value]
        return []

    def set_backend_preference(
        self, names: list[str], *, author: str | None = None
    ) -> None:
        self.set_setting(
            PROJECT_RUNTIME, "backend_preference", list(names), author=author
        )

    def get_tool_manifest_path(self) -> str | None:
        value = self.get_setting(PROJECT_RUNTIME, "tool_manifest_path", default=None)
        return str(value) if value else None

    def get_project_name(self) -> str:
        value = self.get_setting(PROJECT_RUNTIME, "project_name", default="default")
        return str(value) if value else "default"
