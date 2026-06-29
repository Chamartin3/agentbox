"""Resource-scoped data layer.

Resource mixins (ResourcesMixin, SharedResourcesMixin, ResourceBindingsMixin)
have been retired in plan 090_01 — ResourceService now owns the resource domain.

Remaining modules:
- ``_rows.py`` — row-conversion helpers shared with the broader resources package.
- ``models.py`` — dataclasses (Resource, ResourceVersion, ResourceBlob, etc.).
- ``shared/_models.py`` — SharedResourceRecord used by ResourceService and managers.
"""
