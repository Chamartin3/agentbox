"""WorkenvTemplate presets — named, reusable WorkenvConfig snapshots.

Each row stores a complete ``WorkenvConfig`` as a JSON blob plus the
engine (recipe) name.  Seeds are loaded from YAML at startup or via
``agentbox ops workenv seed-presets``.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy.engine import Engine

from agentbox.core.data.utils import now_iso
from agentbox.core.data.schema import workenv_templates

logger = logging.getLogger(__name__)


class WorkenvTemplatesMixin:
    """CRUD for ``workenv_templates`` rows (named WorkenvConfig presets)."""

    engine: Engine

    def list_workenv_templates(self) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                workenv_templates.select()
                .order_by(workenv_templates.c.name)
            )
            return [dict(r._mapping) for r in rows]

    def get_workenv_template(self, name: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                workenv_templates.select().where(
                    workenv_templates.c.name == name
                )
            ).first()
            return dict(row._mapping) if row else None

    def upsert_workenv_template(
        self,
        name: str,
        *,
        engine: str = "claude",
        config_json: dict,
        description: str | None = None,
    ) -> dict:
        now = now_iso()
        existing = self.get_workenv_template(name)
        with self.engine.begin() as conn:
            if existing:
                conn.execute(
                    workenv_templates.update()
                    .where(workenv_templates.c.name == name)
                    .values(
                        description=description,
                        engine=engine,
                        config_json=json.dumps(config_json),
                        updated_at=now,
                    )
                )
            else:
                conn.execute(
                    workenv_templates.insert().values(
                        name=name,
                        description=description or "",
                        engine=engine,
                        config_json=json.dumps(config_json),
                        created_at=now,
                        updated_at=now,
                    )
                )
        result = self.get_workenv_template(name)
        assert result is not None, f"workenv_template {name!r} should exist after upsert"
        return result

    def delete_workenv_template(self, name: str) -> bool:
        with self.engine.begin() as conn:
            result = conn.execute(
                workenv_templates.delete().where(
                    workenv_templates.c.name == name
                )
            )
            return result.rowcount > 0

    def seed_workenv_templates(
        self,
        templates: list[dict],
        *,
        clobber: bool = False,
    ) -> int:
        """Seed templates from a list of dicts.

        Each dict must have ``name``, ``engine``, ``config_json``, and
        optionally ``description``.  Existing templates are skipped unless
        *clobber* is True.
        """
        seeded = 0
        for tmpl in templates:
            existing = self.get_workenv_template(tmpl["name"])
            if existing and not clobber:
                continue
            self.upsert_workenv_template(
                tmpl["name"],
                engine=tmpl.get("engine", "claude"),
                config_json=tmpl["config_json"],
                description=tmpl.get("description"),
            )
            seeded += 1
        return seeded
