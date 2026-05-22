"""Drop legacy slot='system' resource bindings.

Revision ID: w2x6y0z1a2b3
Revises: v1w5x9y0z1a2
Create Date: 2026-06-02 19:30:00.000000

The DB-as-source-of-truth migration left ``slot='system'`` rows in
``agent_prompt_resource_bindings`` that were created from on-disk
``prompts/system.md`` files. The runtime composer
(``BindingsBundleSource``) and the preview route used to honour those
bindings as an override on top of ``agent_versions.prompt_content``,
which meant every ``edit_prompt`` call wrote to a column nothing read.

The composer and preview were fixed to always read
``agent_versions.prompt_content``. This migration removes the now-dead
shadow rows so the data shape matches the runtime contract: there is
no legitimate ``slot='system'`` binding anymore. ``prompt_content`` is
the only system-prompt source.

Downgrade is a no-op — the deleted rows were dead data; recreating
them would re-introduce the shadow bug.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "w2x6y0z1a2b3"
down_revision: str | Sequence[str] | None = "v1w5x9y0z1a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(name)


def upgrade() -> None:
    if not _has_table("agent_prompt_resource_bindings"):
        return
    op.execute("DELETE FROM agent_prompt_resource_bindings WHERE slot='system'")


def downgrade() -> None:
    # No-op: the deleted rows were dead data (shadowing prompt_content).
    pass
