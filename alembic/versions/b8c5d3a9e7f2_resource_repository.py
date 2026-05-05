"""Add central resource repository tables.

Revision ID: b8c5d3a9e7f2
Revises: a7b3d2e8f1c4
Create Date: 2026-05-22 19:00:00.000000

Foundation for the resources-refactor (Plan 01). Adds:
- resources: logical, named, typed resource records
- resource_versions: immutable per-version metadata + changelog
- resource_blobs: per-version file contents (DB BYTEA)
- active_resource_versions: pointer to the currently active version per resource
- runs.resource_snapshot: JSON snapshot of resolved resources at run start
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8c5d3a9e7f2"
down_revision: str | Sequence[str] | None = "a7b3d2e8f1c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "resources",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("tags", sa.String(), nullable=True),
        sa.Column("active_version_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.CheckConstraint(
            "type IN ('document', 'folder', 'skill')",
            name="resources_type_check",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_resources_slug"),
    )
    op.create_index("ix_resources_type", "resources", ["type"])
    op.create_index("ix_resources_status", "resources", ["status"])

    op.create_table(
        "resource_versions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("resource_id", sa.String(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("is_draft", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("import_source", sa.String(), nullable=False),
        sa.Column("source_metadata", sa.String(), nullable=True),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata_json", sa.String(), nullable=True),
        sa.Column("changelog", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.CheckConstraint(
            "import_source IN ('upload', 'host_path', 'toml_migration', 'db_only')",
            name="resource_versions_import_source_check",
        ),
        sa.CheckConstraint("is_draft IN (0, 1)", name="resource_versions_is_draft_bool"),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "resource_id", "version_number", name="uq_resource_versions_number"
        ),
    )
    op.create_index(
        "ix_resource_versions_resource", "resource_versions", ["resource_id"]
    )

    op.create_table(
        "resource_blobs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("resource_version_id", sa.String(), nullable=False),
        sa.Column("relative_path", sa.String(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("content_text", sa.String(), nullable=True),
        sa.Column("mime_type", sa.String(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["resource_version_id"],
            ["resource_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "resource_version_id",
            "relative_path",
            name="uq_resource_blobs_path",
        ),
    )
    op.create_index(
        "ix_resource_blobs_version", "resource_blobs", ["resource_version_id"]
    )

    op.create_table(
        "active_resource_versions",
        sa.Column("resource_id", sa.String(), nullable=False),
        sa.Column("version_id", sa.String(), nullable=False),
        sa.Column("activated_at", sa.String(), nullable=False),
        sa.Column("activated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.id"]),
        sa.ForeignKeyConstraint(["version_id"], ["resource_versions.id"]),
        sa.PrimaryKeyConstraint("resource_id"),
    )

    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("resource_snapshot", sa.String(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.drop_column("resource_snapshot")

    op.drop_table("active_resource_versions")
    op.drop_index("ix_resource_blobs_version", table_name="resource_blobs")
    op.drop_table("resource_blobs")
    op.drop_index("ix_resource_versions_resource", table_name="resource_versions")
    op.drop_table("resource_versions")
    op.drop_index("ix_resources_status", table_name="resources")
    op.drop_index("ix_resources_type", table_name="resources")
    op.drop_table("resources")
