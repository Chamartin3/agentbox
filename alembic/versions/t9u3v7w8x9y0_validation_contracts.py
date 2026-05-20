"""Add validation_contracts + agent_version_validation_bindings.

Revision ID: t9u3v7w8x9y0
Revises: s8t2u6v7w8x9
Create Date: 2026-05-31 12:00:00.000000

Validation contracts (rules + validator) are a reusable entity bound to
agent versions per direction (input/output). Schema validation stays in
agent_prompt_resource_bindings (slot='input_schema'/'output_schema');
rules + validator move out of config_json["output"] into this dedicated
model so they can be shared across agents and edited independently.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "t9u3v7w8x9y0"
down_revision: str | Sequence[str] | None = "s8t2u6v7w8x9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(name)


def _has_index(table: str, name: str) -> bool:
    bind = op.get_bind()
    return any(ix["name"] == name for ix in sa.inspect(bind).get_indexes(table))


def upgrade() -> None:
    # Idempotent: SessionStore.metadata.create_all() may have created these
    # tables on older DBs that booted before alembic was actually wired in.
    if _has_table("validation_contracts") and _has_table(
        "agent_version_validation_bindings"
    ):
        return
    op.create_table(
        "validation_contracts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("rules", sa.String(), nullable=False, server_default="[]"),
        sa.Column("validators", sa.String(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.UniqueConstraint("name", name="uq_validation_contracts_name"),
    )

    op.create_table(
        "agent_version_validation_bindings",
        sa.Column(
            "agent_version_id",
            sa.Integer(),
            sa.ForeignKey("agent_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("direction", sa.String(), nullable=False),
        sa.Column(
            "contract_id",
            sa.String(),
            sa.ForeignKey("validation_contracts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.CheckConstraint(
            "direction IN ('input', 'output')",
            name="agent_version_validation_direction_check",
        ),
        sa.UniqueConstraint(
            "agent_version_id", "direction", name="pk_agent_version_validation"
        ),
    )
    op.create_index(
        "ix_agent_version_validation_version",
        "agent_version_validation_bindings",
        ["agent_version_id"],
    )
    op.create_index(
        "ix_agent_version_validation_contract",
        "agent_version_validation_bindings",
        ["contract_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agent_version_validation_contract",
        table_name="agent_version_validation_bindings",
    )
    op.drop_index(
        "ix_agent_version_validation_version",
        table_name="agent_version_validation_bindings",
    )
    op.drop_table("agent_version_validation_bindings")
    op.drop_table("validation_contracts")
