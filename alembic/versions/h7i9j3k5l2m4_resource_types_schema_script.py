"""Extend resources.type enum with `schema` and `script`.

Revision ID: h7i9j3k5l2m4
Revises: g6h8i2j4k1l3
Create Date: 2026-05-23 20:00:00.000000

Foundation for the resources overhaul (RESOURCES_PLAN.md Phase 0).
Adds two new resource types so JSON Schema documents and python/shell
scripts can be tracked through the unified resources pipeline.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "h7i9j3k5l2m4"
down_revision: str | Sequence[str] | None = "g6h8i2j4k1l3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("resources") as batch:
        batch.drop_constraint("resources_type_check", type_="check")
        batch.create_check_constraint(
            "resources_type_check",
            "type IN ('document', 'folder', 'skill', 'schema', 'script')",
        )


def downgrade() -> None:
    with op.batch_alter_table("resources") as batch:
        batch.drop_constraint("resources_type_check", type_="check")
        batch.create_check_constraint(
            "resources_type_check",
            "type IN ('document', 'folder', 'skill')",
        )
