"""Generation payload types — re-exported from agentbox.core.data.workenv.

Canonical definitions live in ``core.data.workenv`` so ``engines.backends``
can import them without creating a cycle through ``workspaces.generation``.
"""

from __future__ import annotations

from agentbox.core.data.workenv import (
    Item as Item,
    RenderedDir as RenderedDir,
    Role as Role,
)
