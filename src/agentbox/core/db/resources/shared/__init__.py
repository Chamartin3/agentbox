"""Shared resources mixin — composed into SessionStore."""

from agentbox.core.db.resources.shared._models import (
    SharedResourceRecord,
    row_to_record,
)
from agentbox.core.db.resources.shared.lookup import SharedResourceLookupMixin
from agentbox.core.db.resources.shared.write import SharedResourceWriteMixin

__all__ = [
    "SharedResourceRecord",
    "SharedResourcesMixin",
    "row_to_record",
]


class SharedResourcesMixin(
    SharedResourceLookupMixin,
    SharedResourceWriteMixin,
):
    """
    .. deprecated::
        Use ``db.shared_resources`` manager methods instead.

    Versioned shared resource persistence. Requires ``self.engine: Engine``."""
