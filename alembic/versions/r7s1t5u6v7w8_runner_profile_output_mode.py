"""Add runner_profiles.output_mode.

Revision ID: r7s1t5u6v7w8
Revises: p5q9r1s3t0u4
Create Date: 2026-05-27 20:30:00.000000

Lets a profile pin how structured output is enforced when the token
backend builds a pydantic-ai Agent:

- ``auto``  — default; preserves existing behavior (tool-call output).
- ``tool``  — explicit tool-call mode (same as ``auto`` today).
- ``prompted`` — schema injected into the prompt; model returns JSON in
  text. Needed for reasoning models (e.g. DeepSeek V4 Pro) that reject
  forced ``tool_choice``.
- ``native`` — provider-native structured output mode.

Default ``auto`` means no existing profile changes behavior.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "r7s1t5u6v7w8"
down_revision: str | Sequence[str] | None = "p5q9r1s3t0u4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("runner_profiles") as batch:
        batch.add_column(
            sa.Column(
                "output_mode",
                sa.String(),
                nullable=False,
                server_default="auto",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("runner_profiles") as batch:
        batch.drop_column("output_mode")
