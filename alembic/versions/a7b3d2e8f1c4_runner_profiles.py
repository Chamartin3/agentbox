"""Add runner_profiles and agent_runner_profiles tables

Revision ID: a7b3d2e8f1c4
Revises: f5a2c8d1e9b6
Create Date: 2026-05-22 17:30:00.000000

Introduces runner profile catalog and agent-to-profile associations.
Tables:
- runner_profiles: executor configuration library with backend-specific settings
- agent_runner_profiles: links agents to selected runner profiles
- runs.runner_profile_id: tracks which profile was used for a given run
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7b3d2e8f1c4"
down_revision: Union[str, Sequence[str], None] = "f5a2c8d1e9b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "runner_profiles",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("backend", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), nullable=True),
        sa.Column("base_url", sa.String(), nullable=True),
        sa.Column("api_key_env", sa.String(), nullable=True),
        sa.Column("params_json", sa.String(), nullable=False, server_default="{}"),
        sa.Column("headers_json", sa.String(), nullable=False, server_default="{}"),
        sa.Column("extra_args_json", sa.String(), nullable=False, server_default="[]"),
        sa.Column("is_enabled", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_system_default", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.CheckConstraint("is_enabled IN (0, 1)", name="runner_profiles_is_enabled_bool"),
        sa.CheckConstraint("is_system_default IN (0, 1)", name="runner_profiles_is_system_default_bool"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_runner_profiles_backend_provider",
        "runner_profiles",
        ["backend", "provider"],
    )
    op.create_index(
        "idx_runner_profiles_enabled",
        "runner_profiles",
        ["is_enabled"],
    )

    op.create_table(
        "agent_runner_profiles",
        sa.Column("agent_id", sa.String(), nullable=False),
        sa.Column("runner_profile_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["runner_profile_id"], ["runner_profiles.id"]),
        sa.PrimaryKeyConstraint("agent_id"),
    )

    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("runner_profile_id", sa.String(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_runs_runner_profile_id",
            "runner_profiles",
            ["runner_profile_id"],
            ["id"],
        )
        batch_op.create_index(
            "idx_runs_runner_profile_id",
            ["runner_profile_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.drop_index("idx_runs_runner_profile_id")
        batch_op.drop_constraint("fk_runs_runner_profile_id", type_="foreignkey")
        batch_op.drop_column("runner_profile_id")

    op.drop_index("idx_runner_profiles_enabled")
    op.drop_index("idx_runner_profiles_backend_provider")
    op.drop_table("agent_runner_profiles")
    op.drop_table("runner_profiles")
