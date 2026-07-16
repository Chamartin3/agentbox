"""Agent version and version-file models + managers.

Maps to the ``agent_versions``, ``agent_version_files``,
``agent_version_ratings``, and ``agent_version_comments`` tables.
"""
from __future__ import annotations

from typing import Optional, Unpack

from sqlalchemy import JSON, Row, func, select, update as sa_update
from sqlalchemy.engine import Connection
from sqlalchemy import UniqueConstraint

from agentbox.core.db.base.tablename import tablename, tableargs
from sqlmodel import Field, Index, CheckConstraint

from agentbox.core.db.base.model import Entity
from agentbox.core.db.base.manager import Manager
from agentbox.core.data._util import now_iso
from agentbox.core.data.rows import (
	AgentVersionCommentRow,
	AgentVersionFileRow,
	AgentVersionRatingRow,
	AgentVersionRow,
	_AgentVersionCommentFields,
	_AgentVersionFields,
	_AgentVersionRatingFields,
)
from agentbox.core.db.agents.agent import ActiveAgentVersion


class AgentVersion(Entity, table=True):
	"""A versioned snapshot of an agent's definition and prompt content."""

	__tablename__ = tablename("agent_versions")

	id: int = Field(default=None, primary_key=True)
	agent_id: str = Field(nullable=False)
	version: int = Field(nullable=False)
	source_path: str = Field(nullable=False)
	source_format: str = Field(nullable=False)
	content_snapshot: str = Field(nullable=False)
	prompt_snapshot: str = Field(nullable=False)
	content_hash: str = Field(nullable=False)
	author: str = Field(nullable=False)
	changelog: str = Field(nullable=False, default="", sa_column_kwargs={"server_default": ""})
	is_legacy: int = Field(nullable=False, default=0, sa_column_kwargs={"server_default": "0"})
	created_at: str = Field(nullable=False)
	config_json: Optional[str] = Field(default=None)
	prompt_content: Optional[str] = Field(default=None)
	source: str = Field(nullable=False, default="manifest", sa_column_kwargs={"server_default": "manifest"})
	resolved_tool_grants: Optional[list[str]] = Field(default=None, sa_type=JSON)

	__table_args__ = tableargs(
		Index("idx_agent_versions_agent", "agent_id", "version", unique=True),
	)


class AgentVersionFile(Entity, table=True):
	"""A file attached to a particular agent version."""

	__tablename__ = tablename("agent_version_files")

	id: int = Field(default=None, primary_key=True)
	version_id: int = Field(foreign_key="agent_versions.id", ondelete="CASCADE", nullable=False)
	relative_path: str = Field(nullable=False)
	kind: str = Field(nullable=False)
	content: str = Field(nullable=False)
	sha256: str = Field(nullable=False)
	source_uri: Optional[str] = Field(default=None)
	position: int = Field(nullable=False, default=0, sa_column_kwargs={"server_default": "0"})
	created_at: str = Field(nullable=False)

	__table_args__ = tableargs(
		UniqueConstraint("version_id", "relative_path", name="uq_version_file_path"),
		Index("idx_agent_version_files_version", "version_id"),
	)


class AgentVersionRating(Entity, table=True):
	"""A user rating (1-5) for an agent version."""

	__tablename__ = tablename("agent_version_ratings")

	version_id: int = Field(foreign_key="agent_versions.id", primary_key=True)
	rating: int = Field(nullable=False)
	rater: str = Field(nullable=False)
	rated_at: str = Field(nullable=False)

	__table_args__ = tableargs(
		CheckConstraint("rating BETWEEN 1 AND 5", name="rating_range"),
	)


class AgentVersionComment(Entity, table=True):
	"""A user comment on an agent version."""

	__tablename__ = tablename("agent_version_comments")

	id: int = Field(default=None, primary_key=True)
	version_id: int = Field(foreign_key="agent_versions.id", nullable=False)
	author: str = Field(nullable=False)
	body: str = Field(nullable=False)
	created_at: str = Field(nullable=False)


agent_versions = AgentVersion.__table__
agent_version_files = AgentVersionFile.__table__
agent_version_ratings = AgentVersionRating.__table__
agent_version_comments = AgentVersionComment.__table__
active_agent_versions = ActiveAgentVersion.__table__


def _version_row(row: Row) -> AgentVersionRow:
	"""Shape an ``agent_versions`` row into the ``AgentVersionRow`` contract.

	Built field-by-field from the row mapping (the SELECT projects exactly the
	``agent_versions`` columns), so no cast or type-ignore is needed.
	"""
	m = row._mapping
	return AgentVersionRow(
		id=m["id"],
		agent_id=m["agent_id"],
		version=m["version"],
		source_path=m["source_path"],
		source_format=m["source_format"],
		content_snapshot=m["content_snapshot"],
		prompt_snapshot=m["prompt_snapshot"],
		content_hash=m["content_hash"],
		author=m["author"],
		changelog=m["changelog"],
		is_legacy=bool(m["is_legacy"]),
		created_at=m["created_at"],
		config_json=m["config_json"],
		prompt_content=m["prompt_content"],
		source=m["source"],
		resolved_tool_grants=m["resolved_tool_grants"],
	)


def _file_row(row: Row) -> AgentVersionFileRow:
	"""Shape an ``agent_version_files`` row into the ``AgentVersionFileRow`` contract."""
	m = row._mapping
	return AgentVersionFileRow(
		id=m["id"],
		version_id=m["version_id"],
		relative_path=m["relative_path"],
		kind=m["kind"],
		content=m["content"],
		sha256=m["sha256"],
		source_uri=m["source_uri"],
		position=m["position"],
		created_at=m["created_at"],
	)


def _comment_row(row: Row) -> AgentVersionCommentRow:
	"""Shape an ``agent_version_comments`` row into the typed contract."""
	m = row._mapping
	return AgentVersionCommentRow(
		id=m["id"],
		version_id=m["version_id"],
		author=m["author"],
		body=m["body"],
		created_at=m["created_at"],
	)


def _rating_row(row: Row) -> AgentVersionRatingRow:
	"""Shape an ``agent_version_ratings`` row into the typed contract."""
	m = row._mapping
	return AgentVersionRatingRow(
		version_id=m["version_id"],
		rating=m["rating"],
		rater=m["rater"],
		rated_at=m["rated_at"],
	)


def _insert_files(conn: Connection, version_id: int, prepared: list[dict]) -> None:
	"""Bulk-insert prepared file rows for ``version_id`` (adds created_at)."""
	if not prepared:
		return
	conn.execute(
		agent_version_files.insert(),
		[
			{**row, "version_id": version_id, "created_at": now_iso()}
			for row in prepared
		],
	)


def _copy_files(conn: Connection, src_version_id: int, dst_version_id: int) -> None:
	"""Copy all ``agent_version_files`` rows from ``src`` to ``dst``."""
	files = conn.execute(
		agent_version_files.select().where(
			agent_version_files.c.version_id == src_version_id
		)
	).fetchall()
	if not files:
		return
	conn.execute(
		agent_version_files.insert(),
		[
			{
				"version_id": dst_version_id,
				"relative_path": f._mapping["relative_path"],
				"kind": f._mapping["kind"],
				"content": f._mapping["content"],
				"sha256": f._mapping["sha256"],
				"source_uri": f._mapping.get("source_uri"),
				"position": f._mapping.get("position", 0),
				"created_at": now_iso(),
			}
			for f in files
		],
	)


class AgentVersionManager(Manager[AgentVersion]):
	"""Manager for the ``agent_versions`` table.

	Reads return shaped dicts to match callers; resolution policy (active
	vs latest fallback, hidden-agent filtering) lives in ``AgentService``.
	"""

	model = AgentVersion

	def latest_for_agent(self, agent_id: str) -> AgentVersion | None:
		"""Return the highest version number for an agent, or None."""
		stmt = (
			select(AgentVersion)
			.where(getattr(AgentVersion, "agent_id") == agent_id)
			.order_by(getattr(AgentVersion, "version").desc())  # sqlalchemy: Column.desc() not in stubs
			.limit(1)
		)
		return self._scalar(stmt)

	def exists_for_agent(self, agent_id: str) -> bool:
		"""True if the agent has any version history."""
		with self._engine.connect() as conn:
			return (
				conn.execute(
					agent_versions.select()
					.where(agent_versions.c.agent_id == agent_id)
					.limit(1)
				).first()
				is not None
			)

	def get_latest(self, agent_id: str) -> AgentVersionRow | None:
		with self._engine.connect() as conn:
			row = conn.execute(
				agent_versions.select()
				.where(agent_versions.c.agent_id == agent_id)
				.order_by(agent_versions.c.version.desc())
				.limit(1)
			).first()
			return _version_row(row) if row else None

	def get_active(self, agent_id: str) -> AgentVersionRow | None:
		"""Row pointed at by ``active_agent_versions``, or None if unset."""
		with self._engine.connect() as conn:
			pointer = conn.execute(
				active_agent_versions.select().where(
					active_agent_versions.c.agent_id == agent_id
				)
			).first()
			if pointer is None:
				return None
			row = conn.execute(
				agent_versions.select().where(
					agent_versions.c.id == pointer._mapping["version_id"]
				)
			).first()
			return _version_row(row) if row else None

	def get_effective_active(self, agent_id: str) -> AgentVersionRow | None:
		"""The version to treat as active: the explicit ``active_agent_versions``
		pointer, or the latest version when none was ever activated (versions
		created but not promoted, or legacy agents imported before the pointer
		table was populated). This is the one resolution rule — readers wanting
		"the active version" call this instead of composing ``get_active or
		get_latest`` inline."""
		return self.get_active(agent_id) or self.get_latest(agent_id)

	def get_by_id(self, version_id: int) -> AgentVersionRow | None:
		with self._engine.connect() as conn:
			row = conn.execute(
				agent_versions.select().where(agent_versions.c.id == version_id)
			).first()
			return _version_row(row) if row else None

	def get_by_number(self, agent_id: str, version: int) -> AgentVersionRow | None:
		with self._engine.connect() as conn:
			row = conn.execute(
				agent_versions.select().where(
					agent_versions.c.agent_id == agent_id,
					agent_versions.c.version == version,
				)
			).first()
			return _version_row(row) if row else None

	def list_for_agent(self, agent_id: str) -> list[AgentVersionRow]:
		with self._engine.connect() as conn:
			rows = conn.execute(
				agent_versions.select()
				.where(agent_versions.c.agent_id == agent_id)
				.order_by(agent_versions.c.version.desc())
			)
			return [_version_row(r) for r in rows]

	def set_active(self, agent_id: str, version_id: int) -> None:
		"""Set a version as the active version for an agent."""
		stmt = (
			sa_update(AgentVersion)
			.where(getattr(AgentVersion, "agent_id") == agent_id)
			.values(version_id=version_id, activated_at=now_iso())
		)
		self._query(stmt)

	def next_version(self, agent_id: str) -> int:
		"""Max(version)+1 for an agent (1 when it has no history)."""
		with self._engine.connect() as conn:
			row = conn.execute(
				select(func.coalesce(func.max(agent_versions.c.version), 0)).where(
					agent_versions.c.agent_id == agent_id
				)
			).first()
			return int(row[0]) + 1 if row else 1

	def list_latest_per_agent(self) -> list[AgentVersionRow]:
		"""One row per agent_id — its highest-numbered version snapshot.

		No hidden-agent filtering here; the deleted/disabled policy lives in
		``AgentService.list_agents_with_latest``.
		"""
		with self._engine.connect() as conn:
			inner = (
				select(
					agent_versions.c.agent_id,
					func.max(agent_versions.c.version).label("max_version"),
				)
				.group_by(agent_versions.c.agent_id)
				.subquery()
			)
			q = (
				agent_versions.select()
				.join(
					inner,
					(agent_versions.c.agent_id == inner.c.agent_id)
					& (agent_versions.c.version == inner.c.max_version),
				)
				.order_by(agent_versions.c.created_at.desc())
			)
			return [_version_row(r) for r in conn.execute(q)]

	def insert_version(
		self,
		*,
		copy_files_from: int | None = None,
		files: list[dict] | None = None,
		activate_for: str | None = None,
		activated_at: str | None = None,
		**fields: Unpack[_AgentVersionFields],
	) -> int:
		"""Insert one version row and return the new id.

		Atomic, in a single txn, because a partial write breaks an invariant:
		a version and its files (copied or inserted) and, when
		``activate_for`` is set, the active-pointer swap must all land or none
		of them do. ``activated_at`` must be supplied when ``activate_for`` is.
		"""
		with self._engine.begin() as conn:
			result = conn.execute(agent_versions.insert().values(**fields))
			pk = result.inserted_primary_key
			assert pk is not None
			version_id = int(pk[0])
			if copy_files_from is not None:
				_copy_files(conn, copy_files_from, version_id)
			if files:
				_insert_files(conn, version_id, files)
			if activate_for is not None:
				assert activated_at is not None
				conn.execute(
					active_agent_versions.delete().where(
						active_agent_versions.c.agent_id == activate_for
					)
				)
				conn.execute(
					active_agent_versions.insert().values(
						agent_id=activate_for,
						version_id=version_id,
						activated_at=activated_at,
					)
				)
			return version_id

	def patch(self, version_id: int, **values: Unpack[_AgentVersionFields]) -> None:
		"""Update the supplied columns on one version row."""
		with self._engine.begin() as conn:
			conn.execute(
				agent_versions.update()
				.where(agent_versions.c.id == version_id)
				.values(**values)
			)


class AgentVersionFileManager(Manager[AgentVersionFile]):
	"""Manager for the ``agent_version_files`` table — pure row ops.

	File validation/preparation (kind checks, sha256, dedupe) is policy and
	lives in ``AgentService``; these methods take already-prepared rows.
	"""
	model = AgentVersionFile

	def list_for_version(self, version_id: int) -> list[AgentVersionFileRow]:
		with self._engine.connect() as conn:
			rows = conn.execute(
				agent_version_files.select()
				.where(agent_version_files.c.version_id == version_id)
				.order_by(agent_version_files.c.position, agent_version_files.c.id)
			)
			return [_file_row(r) for r in rows.fetchall()]

	def insert_files(self, version_id: int, prepared: list[dict]) -> None:
		with self._engine.begin() as conn:
			_insert_files(conn, version_id, prepared)

	def replace_files(self, version_id: int, prepared: list[dict]) -> None:
		"""Atomically swap a version's files (delete-all + insert in one txn).

		Kept atomic — a crash between delete and insert would leave the
		version with zero files, breaking rendering.
		"""
		with self._engine.begin() as conn:
			conn.execute(
				agent_version_files.delete().where(
					agent_version_files.c.version_id == version_id
				)
			)
			_insert_files(conn, version_id, prepared)

	def delete_for_version(self, version_id: int) -> None:
		with self._engine.begin() as conn:
			conn.execute(
				agent_version_files.delete().where(
					agent_version_files.c.version_id == version_id
				)
			)

	def delete_file(self, file_id: int) -> None:
		with self._engine.begin() as conn:
			conn.execute(
				agent_version_files.delete().where(agent_version_files.c.id == file_id)
			)


class AgentVersionRatingManager(Manager[AgentVersionRating]):
	"""Manager for the ``agent_version_ratings`` table — pure row ops."""
	model = AgentVersionRating

	def latest_for_version(self, version_id: int) -> AgentVersionRatingRow | None:
		with self._engine.connect() as conn:
			row = conn.execute(
				agent_version_ratings.select().where(
					agent_version_ratings.c.version_id == version_id
				)
			).first()
			return _rating_row(row) if row else None

	def insert(self, **fields: Unpack[_AgentVersionRatingFields]) -> None:
		with self._engine.begin() as conn:
			conn.execute(agent_version_ratings.insert().values(**fields))


class AgentVersionCommentManager(Manager[AgentVersionComment]):
	"""Manager for the ``agent_version_comments`` table — pure row ops."""
	model = AgentVersionComment

	def latest_for_version(self, version_id: int) -> AgentVersionCommentRow | None:
		with self._engine.connect() as conn:
			row = conn.execute(
				agent_version_comments.select().where(
					agent_version_comments.c.version_id == version_id
				)
			).first()
			return _comment_row(row) if row else None

	def list_for_version(self, version_id: int) -> list[AgentVersionCommentRow]:
		with self._engine.connect() as conn:
			rows = conn.execute(
				agent_version_comments.select()
				.where(agent_version_comments.c.version_id == version_id)
				.order_by(agent_version_comments.c.created_at)
			)
			return [_comment_row(r) for r in rows.fetchall()]

	def insert(self, **fields: Unpack[_AgentVersionCommentFields]) -> None:
		with self._engine.begin() as conn:
			conn.execute(agent_version_comments.insert().values(**fields))
