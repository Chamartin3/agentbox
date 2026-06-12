"""Version-file CRUD + version create + activate."""

from __future__ import annotations

from sqlalchemy.engine import Engine

from agentbox.core.data.agents.versions.models import _prepare_files
from agentbox.core.data.agents.versions.read import _AgentVersionsReadMixin
from agentbox.core.data.utils import now_iso
from agentbox.core.data.schema import (
    active_agent_versions,
    agent_version_files,
    agent_versions,
)


class _AgentVersionsFilesMixin(_AgentVersionsReadMixin):
    """Manage agent_version_files rows and low-level version inserts."""

    engine: Engine

    def create_version(
        self,
        agent_id: str,
        source_path: str,
        source_format: str,
        content_snapshot: str,
        prompt_snapshot: str,
        content_hash: str,
        author: str = "system",
        changelog: str = "",
        is_legacy: bool = False,
        files: list[dict] | None = None,
        config_json: str | None = None,
        prompt_content: str | None = None,
        source: str = "manifest",
    ) -> dict:
        prepared = _prepare_files(files) if files else []
        version = self._next_version(agent_id)
        with self.engine.begin() as conn:
            result = conn.execute(
                agent_versions.insert().values(
                    agent_id=agent_id,
                    version=version,
                    source_path=source_path,
                    source_format=source_format,
                    content_snapshot=content_snapshot,
                    prompt_snapshot=prompt_snapshot,
                    content_hash=content_hash,
                    author=author,
                    changelog=changelog,
                    is_legacy=int(is_legacy),
                    created_at=now_iso(),
                    config_json=config_json,
                    prompt_content=prompt_content,
                    source=source,
                )
            )
            pk = result.inserted_primary_key
            assert pk is not None
            version_id = int(pk[0])
            if prepared:
                conn.execute(
                    agent_version_files.insert(),
                    [
                        {**row, "version_id": version_id, "created_at": now_iso()}
                        for row in prepared
                    ],
                )
        created = self.get_version(agent_id, version)
        assert created is not None
        return created

    def insert_version_files(self, version_id: int, files: list[dict]) -> None:
        prepared = _prepare_files(files)
        if not prepared:
            return
        with self.engine.begin() as conn:
            conn.execute(
                agent_version_files.insert(),
                [
                    {**row, "version_id": version_id, "created_at": now_iso()}
                    for row in prepared
                ],
            )

    def replace_version_files(self, version_id: int, files: list[dict]) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                agent_version_files.delete().where(
                    agent_version_files.c.version_id == version_id
                )
            )
        if files:
            self.insert_version_files(version_id, files)

    def delete_version_files(self, version_id: int) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                agent_version_files.delete().where(
                    agent_version_files.c.version_id == version_id
                )
            )

    def delete_version_file(self, file_id: int) -> None:
        """Delete a single version file by ID."""
        with self.engine.begin() as conn:
            conn.execute(
                agent_version_files.delete().where(agent_version_files.c.id == file_id)
            )

    def replace_version_config(self, version_id: int, config_json: str) -> None:
        """Replace the config_json for a version in-place.

        Used by migrate-to-db-only to populate config_json on versions that
        predate DB-as-source-of-truth.
        """
        with self.engine.begin() as conn:
            conn.execute(
                agent_versions.update()
                .where(agent_versions.c.id == version_id)
                .values(config_json=config_json)
            )

    def activate_version(self, agent_id: str, version_id: int) -> None:
        """Pin *version_id* as the active version for *agent_id*."""
        with self.engine.begin() as conn:
            conn.execute(
                active_agent_versions.delete().where(
                    active_agent_versions.c.agent_id == agent_id
                )
            )
            conn.execute(
                active_agent_versions.insert().values(
                    agent_id=agent_id,
                    version_id=version_id,
                    activated_at=now_iso(),
                )
            )
