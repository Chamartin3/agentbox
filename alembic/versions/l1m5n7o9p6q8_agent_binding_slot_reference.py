"""Add slot + attach_as_reference to agent_prompt_resource_bindings.

Revision ID: l1m5n7o9p6q8
Revises: k0l4m6n8o5p7
Create Date: 2026-05-24 18:00:00.000000

Adds two columns and relaxes ``marker``/``mode`` to nullable so a binding
can occupy a fixed slot (input_schema / output_schema) without requiring
splice marker. ``attach_as_reference`` marks document/folder bindings
that should also appear in the composed prompt's references section.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "l1m5n7o9p6q8"
down_revision: str | Sequence[str] | None = "k0l4m6n8o5p7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agent_prompt_resource_bindings") as batch:
        batch.alter_column("marker", existing_type=sa.String(), nullable=True)
        batch.alter_column("mode", existing_type=sa.String(), nullable=True)
        batch.add_column(sa.Column("slot", sa.String(), nullable=True))
        batch.add_column(
            sa.Column(
                "attach_as_reference",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch.create_check_constraint(
            "agent_prompt_bindings_slot_check",
            "slot IS NULL OR slot IN ('input_schema', 'output_schema')",
        )
        batch.create_check_constraint(
            "agent_prompt_bindings_slot_or_marker",
            "(slot IS NOT NULL) OR (marker IS NOT NULL AND mode IS NOT NULL)",
        )
        batch.create_check_constraint(
            "agent_prompt_bindings_reference_bool",
            "attach_as_reference IN (0, 1)",
        )

    op.create_index(
        "uq_agent_prompt_bindings_slot",
        "agent_prompt_resource_bindings",
        ["agent_id", "slot"],
        unique=True,
        sqlite_where=sa.text("slot IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_agent_prompt_bindings_slot",
        table_name="agent_prompt_resource_bindings",
    )
    with op.batch_alter_table("agent_prompt_resource_bindings") as batch:
        batch.drop_constraint(
            "agent_prompt_bindings_reference_bool", type_="check"
        )
        batch.drop_constraint(
            "agent_prompt_bindings_slot_or_marker", type_="check"
        )
        batch.drop_constraint(
            "agent_prompt_bindings_slot_check", type_="check"
        )
        batch.drop_column("attach_as_reference")
        batch.drop_column("slot")
        batch.alter_column("mode", existing_type=sa.String(), nullable=False)
        batch.alter_column("marker", existing_type=sa.String(), nullable=False)
