"""Non-domain utility functions used across the ``core.db`` package.

``now_iso`` now lives in ``core.data._util`` and is re-exported here for
backward compatibility. All new code should import from ``core.data``.
"""

from __future__ import annotations

from agentbox.core.data._util import now_iso  # noqa: F401
