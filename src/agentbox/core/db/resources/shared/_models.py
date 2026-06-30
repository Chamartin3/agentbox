"""Backward-compat shim — SharedResourceRecord moved to core.data (plan 109 Phase A).

All internal and external callers should now import from ``agentbox.core.data``.
This module re-exports for the transition period so existing deep imports do not
break (e.g. ``tests/unit/core/db/test_records.py``, manager internals).
"""
from __future__ import annotations

# ponytail: transitional — remove this shim when all callers point at core.data
from agentbox.core.data.records import SharedResourceRecord as SharedResourceRecord
from agentbox.core.data.records import row_to_shared_resource as row_to_record  # re-exported for backward compat

__all__ = ["SharedResourceRecord", "row_to_record"]
