"""Add settings, api_tokens, agent_config_events, and provider/run FK extras.

Revision ID: k0l4m6n8o5p7
Revises: j9k3l5m7n4o6
Create Date: 2026-05-24 12:00:00.000000

- ``settings``               — generic key/value settings sectioned by domain
                               (e.g. ``runtime_defaults.default_model_*``).
- ``api_tokens``             — environment-scoped API token registry.
- ``agent_config_events``    — audit log of agent-config field changes.
- ``runner_profiles.api_token_id`` — FK to api_tokens (IMPROVEMENTS D6).
- ``runs.prompt_version_id`` — FK to prompt_versions for the runs version
                               source-of-truth migration (IMPROVEMENTS E4).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "k0l4m6n8o5p7"
down_revision: str | Sequence[str] | None = "j9k3l5m7n4o6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_config_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("agent_id", sa.String(), nullable=False),
        sa.Column("field", sa.String(), nullable=False),
        sa.Column("from_value", sa.String(), nullable=True),
        sa.Column("to_value", sa.String(), nullable=True),
        sa.Column("author", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
    )
    op.create_index(
        "ix_agent_config_events_agent",
        "agent_config_events",
        ["agent_id"],
    )
    op.create_index(
        "ix_agent_config_events_created",
        "agent_config_events",
        ["created_at"],
    )

    op.create_table(
        "api_tokens",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("environment", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("secret_encrypted", sa.String(), nullable=False),
        sa.Column("last_four", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.UniqueConstraint(
            "environment", "name", name="uq_api_tokens_env_name"
        ),
    )

    op.create_table(
        "settings",
        sa.Column("section", sa.String(), primary_key=True),
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("value_json", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.Column("updated_by", sa.String(), nullable=True),
    )

    with op.batch_alter_table("runner_profiles") as batch:
        batch.add_column(sa.Column("api_token_id", sa.String(), nullable=True))

    with op.batch_alter_table("runs") as batch:
        batch.add_column(sa.Column("prompt_version_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("runs") as batch:
        batch.drop_column("prompt_version_id")
    with op.batch_alter_table("runner_profiles") as batch:
        batch.drop_column("api_token_id")
    op.drop_table("settings")
    op.drop_table("api_tokens")
    op.drop_index(
        "ix_agent_config_events_created", table_name="agent_config_events"
    )
    op.drop_index(
        "ix_agent_config_events_agent", table_name="agent_config_events"
    )
    op.drop_table("agent_config_events")
