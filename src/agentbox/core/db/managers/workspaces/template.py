"""WorkenvTemplateManager — work environment template CRUD."""
from __future__ import annotations

import json

from agentbox.core.constants import BackendName
from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.workspaces.template import WorkenvTemplate
from agentbox.core.db.schema import workenv_templates
from agentbox.core.db.utils import now_iso


class WorkenvTemplateManager(Manager[WorkenvTemplate]):
    """Manager for the ``workenv_templates`` table."""

    model = WorkenvTemplate

    # ── pure-DB primitives (ported from WorkenvTemplatesMixin) ──────────

    def list_all(self) -> list[dict]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                workenv_templates.select().order_by(workenv_templates.c.name)
            )
            return [dict(r._mapping) for r in rows]

    def get_by_name(self, name: str) -> dict | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                workenv_templates.select().where(workenv_templates.c.name == name)
            ).first()
            return dict(row._mapping) if row else None

    def upsert(
        self,
        name: str,
        *,
        engine: str = BackendName.CLAUDE_CODE,
        config_json: dict,
        description: str | None = None,
    ) -> dict:
        now = now_iso()
        existing = self.get_by_name(name)
        with self._engine.begin() as conn:
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
        result = self.get_by_name(name)
        assert result is not None, f"workenv_template {name!r} should exist after upsert"
        return result

    def delete_by_name(self, name: str) -> bool:
        with self._engine.begin() as conn:
            result = conn.execute(
                workenv_templates.delete().where(workenv_templates.c.name == name)
            )
            return result.rowcount > 0

    def seed(
        self,
        templates: list[dict],
        *,
        clobber: bool = False,
    ) -> int:
        seeded = 0
        for tmpl in templates:
            existing = self.get_by_name(tmpl["name"])
            if existing and not clobber:
                continue
            self.upsert(
                tmpl["name"],
                engine=tmpl.get("engine", BackendName.CLAUDE_CODE),
                config_json=tmpl["config_json"],
                description=tmpl.get("description"),
            )
            seeded += 1
        return seeded
