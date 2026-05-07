"""Settings store mixin — typed-section key/value persistence.

Replaces ad-hoc manifest fields with a DB table so the UI can edit them
without round-tripping through `agentbox.toml`. Each section is a flat
`{key: value}` dict; values are JSON-encoded strings.
"""

from __future__ import annotations

import json

from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from agentbox.core.data.records import now_iso
from agentbox.core.data.schema import settings as settings_table


class SettingsMixin:
    """CRUD for the `settings` table."""

    def get_settings_section(self, section: str) -> dict:
        """Return all `{key: value}` pairs in a section (empty dict if none)."""
        with self.engine.connect() as conn:
            rows = conn.execute(
                settings_table.select().where(settings_table.c.section == section)
            )
            out: dict = {}
            for r in rows:
                m = r._mapping
                try:
                    out[m["key"]] = json.loads(m["value_json"])
                except (json.JSONDecodeError, TypeError):
                    out[m["key"]] = m["value_json"]
            return out

    def get_setting(self, section: str, key: str, default=None):
        """Return one setting value, or `default` if not present."""
        with self.engine.connect() as conn:
            row = conn.execute(
                settings_table.select().where(
                    (settings_table.c.section == section)
                    & (settings_table.c.key == key)
                )
            ).first()
            if row is None:
                return default
            try:
                return json.loads(row._mapping["value_json"])
            except (json.JSONDecodeError, TypeError):
                return row._mapping["value_json"]

    def set_setting(
        self, section: str, key: str, value, *, author: str | None = None
    ) -> None:
        """Upsert a single setting."""
        ts = now_iso()
        payload = json.dumps(value)
        with self.engine.begin() as conn:
            stmt = sqlite_insert(settings_table).values(
                section=section,
                key=key,
                value_json=payload,
                updated_at=ts,
                updated_by=author,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["section", "key"],
                set_={
                    "value_json": payload,
                    "updated_at": ts,
                    "updated_by": author,
                },
            )
            conn.execute(stmt)

    def update_settings_section(
        self,
        section: str,
        patch: dict,
        *,
        author: str | None = None,
    ) -> dict:
        """Apply a partial patch to a section (only listed keys change).

        Returns the full section after the patch.
        """
        for key, value in patch.items():
            self.set_setting(section, key, value, author=author)
        return self.get_settings_section(section)

    def list_settings_sections(self) -> list[str]:
        """Return the distinct section names that have at least one key set."""
        with self.engine.connect() as conn:
            rows = conn.execute(
                settings_table.select().with_only_columns(settings_table.c.section).distinct()
            )
            return [r._mapping["section"] for r in rows]
