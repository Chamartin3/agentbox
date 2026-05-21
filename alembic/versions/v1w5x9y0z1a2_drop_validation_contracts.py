"""Drop validation_contracts + agent_version_validation_bindings (Plan 23).

Revision ID: v1w5x9y0z1a2
Revises: u0v4w8x9y0z1
Create Date: 2026-05-31 14:00:00.000000

Plan 23 collapses the validation-contract abstraction. Validators now
live inline on ``agent_versions.config_json["{input,output}"].validators``
(see ``core/agent/config.resolve_output_config`` and
``api/routes/agent_validation``). The one-time
``bin/migrate_inline_validators.py`` script has already copied every
existing binding row into the corresponding agent_version's config_json
on the live DB; this revision removes the now-empty tables.

Downgrade re-creates the empty tables so an older snapshot can still
boot, but no data is reconstructed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "v1w5x9y0z1a2"
down_revision: str | Sequence[str] | None = "u0v4w8x9y0z1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(name)


def _has_index(table: str, name: str) -> bool:
    bind = op.get_bind()
    return any(ix["name"] == name for ix in sa.inspect(bind).get_indexes(table))


def upgrade() -> None:
    if _has_table("agent_version_validation_bindings"):
        if _has_index(
            "agent_version_validation_bindings",
            "ix_agent_version_validation_contract",
        ):
            op.drop_index(
                "ix_agent_version_validation_contract",
                table_name="agent_version_validation_bindings",
            )
        if _has_index(
            "agent_version_validation_bindings",
            "ix_agent_version_validation_version",
        ):
            op.drop_index(
                "ix_agent_version_validation_version",
                table_name="agent_version_validation_bindings",
            )
        op.drop_table("agent_version_validation_bindings")
    if _has_table("validation_contracts"):
        op.drop_table("validation_contracts")


def downgrade() -> None:
    op.create_table(
        "validation_contracts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
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
