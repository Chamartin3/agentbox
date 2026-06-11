"""Shared resources mixin — composed into SessionStore."""

from agentbox.core.data.resources.shared._models import (
    SharedResourceRecord,
    row_to_record,
)
from agentbox.core.data.resources.shared.lookup import SharedResourceLookupMixin
from agentbox.core.data.resources.shared.write import SharedResourceWriteMixin

__all__ = [
    "SharedResourceRecord",
    "SharedResourcesMixin",
    "row_to_record",
]


class SharedResourcesMixin(
    SharedResourceLookupMixin,
    SharedResourceWriteMixin,
):
    """Versioned shared resource persistence. Requires ``self.engine: Engine``."""
