"""Add agent prompt-embed + workspace file-materialize bindings.

Revision ID: c9d4a2b7e8f5
Revises: b8c5d3a9e7f2
Create Date: 2026-05-22 20:00:00.000000

Plans 02 + 03 — two binding tables that both reference resources.id.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9d4a2b7e8f5"
down_revision: str | Sequence[str] | None = "b8c5d3a9e7f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_prompt_resource_bindings",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("agent_id", sa.String(), nullable=False),
        sa.Column("resource_id", sa.String(), nullable=False),
        sa.Column("marker", sa.String(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("pinned_version_id", sa.String(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("required", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("changelog", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.CheckConstraint(
            "mode IN ('inline', 'skill_primer', 'name_only', 'manifest')",
            name="agent_prompt_bindings_mode_check",
        ),
        sa.CheckConstraint("required IN (0, 1)", name="agent_prompt_bindings_required_bool"),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.id"]),
        sa.ForeignKeyConstraint(["pinned_version_id"], ["resource_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "agent_id", "marker", "resource_id",
            name="uq_agent_prompt_bindings_triple",
        ),
    )
    op.create_index(
        "ix_agent_prompt_bindings_agent",
        "agent_prompt_resource_bindings",
        ["agent_id"],
    )

    op.create_table(
        "workspace_file_resource_bindings",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("resource_id", sa.String(), nullable=False),
        sa.Column("target_path", sa.String(), nullable=True),
        sa.Column("pinned_version_id", sa.String(), nullable=True),
        sa.Column("materialize_mode", sa.String(), nullable=False, server_default="copy"),
        sa.Column("on_conflict", sa.String(), nullable=False, server_default="error"),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("changelog", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.CheckConstraint(
            "materialize_mode IN ('copy', 'symlink', 'mount')",
            name="workspace_file_bindings_mode_check",
        ),
        sa.CheckConstraint(
            "on_conflict IN ('error', 'overwrite', 'skip')",
            name="workspace_file_bindings_on_conflict_check",
        ),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.id"]),
        sa.ForeignKeyConstraint(["pinned_version_id"], ["resource_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "resource_id", "target_path",
            name="uq_workspace_file_bindings_triple",
        ),
    )
    op.create_index(
        "ix_workspace_file_bindings_workspace",
        "workspace_file_resource_bindings",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_workspace_file_bindings_workspace",
        table_name="workspace_file_resource_bindings",
    )
    op.drop_table("workspace_file_resource_bindings")
    op.drop_index(
        "ix_agent_prompt_bindings_agent",
        table_name="agent_prompt_resource_bindings",
    )
    op.drop_table("agent_prompt_resource_bindings")
