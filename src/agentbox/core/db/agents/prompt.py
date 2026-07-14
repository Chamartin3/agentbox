"""PromptVersion model + manager — prompt version history.

Maps to the ``prompt_versions`` table.
"""
from __future__ import annotations

from typing import Optional, Unpack

from sqlalchemy import Row, func, select
from sqlalchemy.engine import Connection

from agentbox.core.db.base.tablename import tablename, tableargs
from sqlmodel import Field, Index

from agentbox.core.db.base.model import Entity
from agentbox.core.db.base.manager import Manager
from agentbox.core.data.rows import PromptVersionRow, _PromptVersionFields
from agentbox.core.db.schema import prompt_versions


class PromptVersion(Entity, table=True):
	"""A versioned snapshot of a prompt's content for an agent."""

	__tablename__ = tablename("prompt_versions")

	id: int = Field(default=None, primary_key=True)
	agent_id: str = Field(nullable=False)
	version: int = Field(nullable=False)
	content: str = Field(nullable=False)
	author: str = Field(nullable=False, default="system")
	changelog: str = Field(nullable=False, default="")
	is_draft: int = Field(nullable=False, default=0)
	content_hash: Optional[str] = Field(default=None)
	created_at: str = Field(nullable=False)

	__table_args__ = tableargs(
		Index("idx_prompt_versions_agent", "agent_id", "version", unique=True),
	)


def _prompt_row(row: Row) -> PromptVersionRow:
	"""Shape a ``prompt_versions`` row into the ``PromptVersionRow`` contract."""
	m = row._mapping
	return PromptVersionRow(
		id=m["id"],
		agent_id=m["agent_id"],
		version=m["version"],
		content=m["content"],
		author=m["author"],
		changelog=m["changelog"],
		is_draft=m["is_draft"],
		content_hash=m["content_hash"],
		created_at=m["created_at"],
	)


class PromptVersionManager(Manager[PromptVersion]):
	"""Manager for the ``prompt_versions`` table — pure row ops."""
	model = PromptVersion

	# ── reads ──────────────────────────────────────────────────────────
	def list_for_agent(self, agent_id: str) -> list[PromptVersionRow]:
		with self._engine.connect() as conn:
			rows = conn.execute(
				prompt_versions.select()
				.where(prompt_versions.c.agent_id == agent_id)
				.order_by(prompt_versions.c.version.desc())
			)
			return [_prompt_row(r) for r in rows.fetchall()]

	def get_by_number(self, agent_id: str, version: int) -> PromptVersionRow | None:
		with self._engine.connect() as conn:
			row = conn.execute(
				prompt_versions.select().where(
					prompt_versions.c.agent_id == agent_id,
					prompt_versions.c.version == version,
				)
			).first()
			return _prompt_row(row) if row else None

	def get_latest_committed(self, agent_id: str) -> PromptVersionRow | None:
		with self._engine.connect() as conn:
			row = conn.execute(
				prompt_versions.select()
				.where(
					prompt_versions.c.agent_id == agent_id,
					prompt_versions.c.is_draft == 0,
				)
				.order_by(prompt_versions.c.version.desc())
				.limit(1)
			).first()
			return _prompt_row(row) if row else None

	def get_draft(self, agent_id: str) -> PromptVersionRow | None:
		with self._engine.connect() as conn:
			row = conn.execute(
				prompt_versions.select()
				.where(
					prompt_versions.c.agent_id == agent_id,
					prompt_versions.c.is_draft == 1,
				)
				.order_by(prompt_versions.c.version.desc())
				.limit(1)
			).first()
			return _prompt_row(row) if row else None

	# ── writes ─────────────────────────────────────────────────────────
	def replace_draft(
		self,
		agent_id: str,
		*,
		content: str,
		content_hash: str,
		author: str,
		changelog: str,
		created_at: str,
	) -> PromptVersionRow:
		"""Atomically drop the agent's draft and insert a fresh one.

		Next version is computed *after* the delete (in-txn) so the freed
		slot is reused, matching the legacy single-draft semantics.
		"""
		with self._engine.begin() as conn:
			conn.execute(
				prompt_versions.delete().where(
					prompt_versions.c.agent_id == agent_id,
					prompt_versions.c.is_draft == 1,
				)
			)
			version = _next_version(conn, agent_id)
			conn.execute(
				prompt_versions.insert().values(
					agent_id=agent_id,
					version=version,
					content=content,
					author=author,
					changelog=changelog,
					is_draft=1,
					content_hash=content_hash,
					created_at=created_at,
				)
			)
			row = conn.execute(
				prompt_versions.select().where(
					prompt_versions.c.agent_id == agent_id,
					prompt_versions.c.version == version,
				)
			).first()
			assert row is not None, f"prompt draft not found after insert for agent {agent_id!r}"
			return _prompt_row(row)

	def insert_committed(
		self,
		agent_id: str,
		*,
		content: str,
		content_hash: str,
		author: str,
		changelog: str,
		created_at: str,
		delete_drafts: bool = False,
	) -> PromptVersionRow:
		"""Insert a committed (non-draft) version, computing the next number
		in-txn. Optionally drops any existing draft first (rollback path)."""
		with self._engine.begin() as conn:
			if delete_drafts:
				conn.execute(
					prompt_versions.delete().where(
						prompt_versions.c.agent_id == agent_id,
						prompt_versions.c.is_draft == 1,
					)
				)
			version = _next_version(conn, agent_id)
			conn.execute(
				prompt_versions.insert().values(
					agent_id=agent_id,
					version=version,
					content=content,
					author=author,
					changelog=changelog,
					is_draft=0,
					content_hash=content_hash,
					created_at=created_at,
				)
			)
			row = conn.execute(
				prompt_versions.select().where(
					prompt_versions.c.agent_id == agent_id,
					prompt_versions.c.version == version,
				)
			).first()
			assert row is not None, f"committed prompt not found after insert for agent {agent_id!r}"
			return _prompt_row(row)

	def patch(self, version_id: int, **values: Unpack[_PromptVersionFields]) -> None:
		"""Update the supplied columns on one prompt-version row."""
		with self._engine.begin() as conn:
			conn.execute(
				prompt_versions.update()
				.where(prompt_versions.c.id == version_id)
				.values(**values)
			)


def _next_version(conn: Connection, agent_id: str) -> int:
	"""Max(version)+1 for an agent, evaluated on the given connection."""
	row = conn.execute(
		select(func.coalesce(func.max(prompt_versions.c.version), 0)).where(
			prompt_versions.c.agent_id == agent_id
		)
	).first()
	return int(row[0]) + 1 if row else 1
