"""Output-schema translation/consistency errors."""

from __future__ import annotations


class UnsupportedSchema(Exception):
    """Raised when a schema uses a construct the converter cannot translate."""


class InconsistentSchema(UnsupportedSchema):
    """Raised when a schema is internally inconsistent (e.g. ``required``
    names a property that is not declared in ``properties``).

    Subclasses :class:`UnsupportedSchema` so callers that already handle
    the broader failure mode keep working; new callers can catch this
    specifically to produce a precise authoring-error message.
    """
