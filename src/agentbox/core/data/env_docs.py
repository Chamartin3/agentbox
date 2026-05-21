"""Env doc mixin (Plan 04).

One structured env doc per workspace, versioned. Same audit pattern as
prompts: every save bumps the version_number and carries a non-empty
changelog. `publish` flips the workspace-scoped active pointer.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from agentbox.core.data.records import now_iso
from agentbox.core.data.schema import workspace_env_doc_versions, workspace_env_docs


def _validate_changelog(s: str) -> str:
    if not s or len(s.strip()) < 3:
        raise ValueError("changelog must be at least 3 characters")
    return s.strip()


class EnvDocsMixin:
    """CRUD + versioning for the per-workspace env doc."""

    engine: Engine

    def get_active_env_doc(self, workspace_id: str) -> dict | None:
        with self.engine.connect() as conn:
            ptr = conn.execute(
                workspace_env_docs.select().where(
                    workspace_env_docs.c.workspace_id == workspace_id
                )
            ).first()
            if not ptr or not ptr.active_version_id:
                return None
            ver = conn.execute(
                workspace_env_doc_versions.select().where(
                    workspace_env_doc_versions.c.id == ptr.active_version_id
                )
            ).first()
            return dict(ver._mapping) if ver else None

    def list_env_doc_versions(self, workspace_id: str) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                workspace_env_doc_versions.select()
                .where(workspace_env_doc_versions.c.workspace_id == workspace_id)
                .order_by(workspace_env_doc_versions.c.version_number.desc())
            )
            return [dict(r._mapping) for r in rows]

    def get_env_doc_version(self, version_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                workspace_env_doc_versions.select().where(
                    workspace_env_doc_versions.c.id == version_id
                )
            ).first()
            return dict(row._mapping) if row else None

    def save_env_doc(
        self,
        workspace_id: str,
        content: dict,
        *,
        changelog: str,
        publish: bool = True,
        actor: str | None = None,
    ) -> dict:
        changelog = _validate_changelog(changelog)
        version_id = uuid.uuid4().hex
        now = now_iso()
        with self.engine.begin() as conn:
            next_num = conn.execute(
                select(
                    func.coalesce(
                        func.max(workspace_env_doc_versions.c.version_number), 0
                    )
                    + 1
                ).where(workspace_env_doc_versions.c.workspace_id == workspace_id)
            ).scalar_one()
            conn.execute(
                workspace_env_doc_versions.insert().values(
                    id=version_id,
                    workspace_id=workspace_id,
                    version_number=next_num,
                    content_json=content,
                    is_draft=0 if publish else 1,
                    changelog=changelog,
                    created_at=now,
                    created_by=actor,
                )
            )
            ptr_exists = conn.execute(
                workspace_env_docs.select().where(
                    workspace_env_docs.c.workspace_id == workspace_id
                )
            ).first()
            if publish:
                if ptr_exists:
                    conn.execute(
                        workspace_env_docs.update()
                        .where(workspace_env_docs.c.workspace_id == workspace_id)
                        .values(active_version_id=version_id)
                    )
                else:
                    conn.execute(
                        workspace_env_docs.insert().values(
                            workspace_id=workspace_id, active_version_id=version_id
                        )
                    )
            elif not ptr_exists:
                conn.execute(
                    workspace_env_docs.insert().values(
                        workspace_id=workspace_id, active_version_id=None
                    )
                )
        row = self.get_env_doc_version(version_id)
        assert row is not None
        return row

    def publish_env_doc(self, workspace_id: str, version_id: str) -> dict:
        with self.engine.begin() as conn:
            ver = conn.execute(
                workspace_env_doc_versions.select().where(
                    (workspace_env_doc_versions.c.id == version_id)
                    & (workspace_env_doc_versions.c.workspace_id == workspace_id)
                )
            ).first()
            if not ver:
                raise ValueError(
                    f"env doc version {version_id!r} not found for workspace"
                )
            conn.execute(
                workspace_env_doc_versions.update()
                .where(workspace_env_doc_versions.c.id == version_id)
                .values(is_draft=0)
            )
            ptr = conn.execute(
                workspace_env_docs.select().where(
                    workspace_env_docs.c.workspace_id == workspace_id
                )
            ).first()
            if ptr:
                conn.execute(
                    workspace_env_docs.update()
                    .where(workspace_env_docs.c.workspace_id == workspace_id)
                    .values(active_version_id=version_id)
                )
            else:
                conn.execute(
                    workspace_env_docs.insert().values(
                        workspace_id=workspace_id, active_version_id=version_id
                    )
                )
        row = self.get_env_doc_version(version_id)
        assert row is not None
        return row

    def rollback_env_doc(
        self,
        workspace_id: str,
        target_version_id: str,
        *,
        changelog: str,
        actor: str | None = None,
    ) -> dict:
        target = self.get_env_doc_version(target_version_id)
        if not target or target["workspace_id"] != workspace_id:
            raise ValueError(
                f"env doc version {target_version_id!r} not found for workspace"
            )
        return self.save_env_doc(
            workspace_id,
            target["content_json"],
            changelog=changelog,
            publish=True,
            actor=actor,
        )
