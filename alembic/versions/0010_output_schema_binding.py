"""Move output_schema_path to resource binding (plan 142).

Revision ID: 0010_output_schema_binding
Revises: 0009_drop_shared_resources
Create Date: 2026-07-09 00:00:00.000000

``output_schema_path`` was a filesystem-path entry in
``agent_versions.config_json["python"]["output_schema_path"]`` that the
runtime resolved by reading the file from disk.  The schema content now
lives in the resources store (``resources`` + ``resource_versions`` +
``resource_blobs``) with the agent referencing it via an
``agent_prompt_resource_bindings`` row where ``slot='output_schema'``.

This migration is a **data backfill** only — no DDL changes are needed
because all target tables already exist.  For each agent version that
carries a non-null ``output_schema_path`` in its ``config_json`` and
whose agent does not yet have an ``output_schema`` slot binding, the
migration:

1. Reads the file from the filesystem (relative to the working
   directory or project root — whichever is accessible at migration
   time).
2. Creates a ``resources`` row (type ``'schema'``, unique slug per
   agent) plus a ``resource_versions`` + ``resource_blobs`` row.
3. Inserts an ``agent_prompt_resource_bindings`` row with
   ``slot='output_schema'`` and ``pinned_version_id`` pointing to the
   new version.

The operation is idempotent:
- It skips agents that already have an ``output_schema`` binding.
- It skips agents whose schema file is not found (logs a warning only).
- ``resources`` rows use a unique slug
  ``__output_schema__{agent_id}`` so re-running is safe.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from alembic import op
import sqlalchemy as sa

revision: str = "0010_output_schema_binding"
down_revision: str | Sequence[str] | None = "0009_drop_shared_resources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger(__name__)

_SLOT = "output_schema"


def _slug_for_agent(agent_id: str) -> str:
    return f"__output_schema__{agent_id}"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _hash_content(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _read_schema_file(path_str: str) -> bytes | None:
    """Try to read the schema file.  Returns None if not found."""
    # Try path as-is first.
    p = Path(path_str)
    if not p.is_absolute():
        # Resolve relative to CWD or AGENTBOX_PROJECT_ROOT.
        root = Path(os.environ.get("AGENTBOX_PROJECT_ROOT", "."))
        p = root / path_str
    if p.is_file():
        return p.read_bytes()
    return None


def upgrade() -> None:
    conn = op.get_bind()
    now = _now()

    # Fetch all agent_versions rows that have output_schema_path set.
    rows = conn.execute(
        sa.text(
            """
            SELECT av.agent_id, av.config_json
            FROM agent_versions av
            WHERE av.config_json IS NOT NULL
              AND json_extract(av.config_json, '$.python.output_schema_path') IS NOT NULL
              AND json_extract(av.config_json, '$.python.output_schema_path') != ''
            GROUP BY av.agent_id
            """
        )
    ).fetchall()

    for row in rows:
        agent_id: str = row[0]
        config_json_raw: str = row[1]

        # Skip if an output_schema binding already exists for this agent.
        existing = conn.execute(
            sa.text(
                """
                SELECT id FROM agent_prompt_resource_bindings
                WHERE agent_id = :agent_id AND slot = :slot
                LIMIT 1
                """
            ),
            {"agent_id": agent_id, "slot": _SLOT},
        ).fetchone()
        if existing:
            logger.debug(
                "output_schema binding already exists for agent %r — skipping",
                agent_id,
            )
            continue

        # Parse config_json to get the path.
        try:
            config = json.loads(config_json_raw)
            path_str: str | None = (
                config.get("python", {}) or {}
            ).get("output_schema_path")
        except (ValueError, TypeError):
            logger.warning(
                "agent %r: could not parse config_json — skipping", agent_id
            )
            continue

        if not path_str:
            continue

        content = _read_schema_file(path_str)
        if content is None:
            logger.warning(
                "agent %r: output_schema_path %r not found at migration time — "
                "binding will be created lazily on first run",
                agent_id,
                path_str,
            )
            continue

        slug = _slug_for_agent(agent_id)
        content_hash = _hash_content(content)

        # Check if the resource slug already exists.
        existing_resource = conn.execute(
            sa.text("SELECT id FROM resources WHERE slug = :slug"),
            {"slug": slug},
        ).fetchone()

        if existing_resource:
            resource_id: str = existing_resource[0]
        else:
            resource_id = uuid.uuid4().hex
            conn.execute(
                sa.text(
                    """
                    INSERT INTO resources
                        (id, slug, type, display_name, description,
                         tags, active_version_id, status, created_at, updated_at)
                    VALUES
                        (:id, :slug, 'schema', :display_name, :description,
                         NULL, NULL, 'active', :now, :now)
                    """
                ),
                {
                    "id": resource_id,
                    "slug": slug,
                    "display_name": f"Output schema for agent {agent_id}",
                    "description": f"Migrated from output_schema_path={path_str!r}",
                    "now": now,
                },
            )

        # Determine next version number.
        max_ver_row = conn.execute(
            sa.text(
                """
                SELECT COALESCE(MAX(version_number), 0)
                FROM resource_versions
                WHERE resource_id = :rid
                """
            ),
            {"rid": resource_id},
        ).fetchone()
        version_number = int(max_ver_row[0]) + 1 if max_ver_row else 1

        version_id = uuid.uuid4().hex
        conn.execute(
            sa.text(
                """
                INSERT INTO resource_versions
                    (id, resource_id, version_number, is_draft, import_source,
                     source_metadata, content_hash, byte_size,
                     metadata_json, changelog, created_at)
                VALUES
                    (:id, :rid, :vnum, 0, 'toml_migration',
                     :src_meta, :chash, :bsize,
                     NULL, :changelog, :now)
                """
            ),
            {
                "id": version_id,
                "rid": resource_id,
                "vnum": version_number,
                "src_meta": json.dumps({"original_path": path_str}),
                "chash": content_hash,
                "bsize": len(content),
                "changelog": f"Backfill from output_schema_path={path_str!r}",
                "now": now,
            },
        )

        blob_id = uuid.uuid4().hex
        conn.execute(
            sa.text(
                """
                INSERT INTO resource_blobs
                    (id, resource_version_id, relative_path, content,
                     content_text, mime_type, size_bytes)
                VALUES
                    (:id, :vid, '', :content, :content_text,
                     'application/json', :bsize)
                """
            ),
            {
                "id": blob_id,
                "vid": version_id,
                "content": content,
                "content_text": content.decode("utf-8", errors="replace"),
                "bsize": len(content),
            },
        )

        # Activate the version.
        conn.execute(
            sa.text(
                """
                DELETE FROM active_resource_versions WHERE resource_id = :rid
                """
            ),
            {"rid": resource_id},
        )
        conn.execute(
            sa.text(
                """
                INSERT INTO active_resource_versions
                    (resource_id, version_id, activated_at)
                VALUES (:rid, :vid, :now)
                """
            ),
            {"rid": resource_id, "vid": version_id, "now": now},
        )
        conn.execute(
            sa.text(
                """
                UPDATE resources
                SET active_version_id = :vid, updated_at = :now
                WHERE id = :rid
                """
            ),
            {"rid": resource_id, "vid": version_id, "now": now},
        )

        # Create the binding.
        binding_id = uuid.uuid4().hex
        conn.execute(
            sa.text(
                """
                INSERT INTO agent_prompt_resource_bindings
                    (id, agent_id, resource_id, marker, mode, slot,
                     attach_as_reference, pinned_version_id, display_order,
                     required, changelog, created_at)
                VALUES
                    (:id, :agent_id, :rid, NULL, NULL, :slot,
                     0, :vid, 0, 1, :changelog, :now)
                """
            ),
            {
                "id": binding_id,
                "agent_id": agent_id,
                "rid": resource_id,
                "slot": _SLOT,
                "vid": version_id,
                "changelog": f"Backfill output_schema binding from {path_str!r}",
                "now": now,
            },
        )

        logger.info(
            "agent %r: created output_schema binding (resource=%r, version=%r)",
            agent_id,
            resource_id,
            version_id,
        )


def downgrade() -> None:
    # Remove only bindings and resources created by this migration
    # (identified by the __output_schema__ slug prefix).
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id FROM resources WHERE slug LIKE '__output_schema__%'"
        )
    ).fetchall()
    for row in rows:
        rid: str = row[0]
        # Delete binding.
        conn.execute(
            sa.text(
                "DELETE FROM agent_prompt_resource_bindings "
                "WHERE resource_id = :rid AND slot = :slot"
            ),
            {"rid": rid, "slot": _SLOT},
        )
        # Delete active version pointer.
        conn.execute(
            sa.text("DELETE FROM active_resource_versions WHERE resource_id = :rid"),
            {"rid": rid},
        )
        # Delete blobs + versions + resource (cascade not guaranteed).
        conn.execute(
            sa.text(
                """
                DELETE FROM resource_blobs
                WHERE resource_version_id IN (
                    SELECT id FROM resource_versions WHERE resource_id = :rid
                )
                """
            ),
            {"rid": rid},
        )
        conn.execute(
            sa.text("DELETE FROM resource_versions WHERE resource_id = :rid"),
            {"rid": rid},
        )
        conn.execute(
            sa.text("DELETE FROM resources WHERE id = :rid"),
            {"rid": rid},
        )
