"""Extend agent_prompt_resource_bindings.slot enum.

Revision ID: o4p8q0r2s9t3
Revises: n3o7p9q1r8s2
Create Date: 2026-05-24 22:00:00.000000

Adds ``system`` and ``user_template`` to the allowed ``slot`` values so
the bundle-deprecation migration can register the system prompt and
user template as bindings instead of bundle file rows.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "o4p8q0r2s9t3"
down_revision: str | Sequence[str] | None = "n3o7p9q1r8s2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agent_prompt_resource_bindings") as batch:
        batch.drop_constraint(
            "agent_prompt_bindings_slot_check", type_="check"
        )
        batch.create_check_constraint(
            "agent_prompt_bindings_slot_check",
            "slot IS NULL OR slot IN ("
            "'system', 'user_template', 'input_schema', 'output_schema'"
            ")",
        )


def downgrade() -> None:
    with op.batch_alter_table("agent_prompt_resource_bindings") as batch:
        batch.drop_constraint(
            "agent_prompt_bindings_slot_check", type_="check"
        )
        batch.create_check_constraint(
            "agent_prompt_bindings_slot_check",
            "slot IS NULL OR slot IN ('input_schema', 'output_schema')",
        )
