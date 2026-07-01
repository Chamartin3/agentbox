"""Operator-configured runtime defaults resolved from the settings store.

Lives in ``core/agent`` (not ``core/constants``) so that constants stays a
pure module of typed enums with no runtime dependencies. Importing this
module must not create a ``core -> api`` cycle.
"""

from __future__ import annotations

import logging

from agentbox.core.db.system.config import load_settings_section

logger = logging.getLogger(__name__)


def runtime_default_model(
    store: object | None, backend_name: str
) -> str | None:
    """Look up an operator-configured default model for a backend.

    Reads the ``runtime_defaults`` settings section for
    ``default_model_<backend>``. Returns ``None`` when the store isn't
    available, the section is missing, or the value is unset. Backends
    fall back to their hard-coded ``default_model`` attribute when this
    returns ``None``.
    """
    if store is None:
        return None
    try:
        section = load_settings_section("runtime_defaults") or {}
    except Exception:
        logger.debug("runtime_default_model: settings lookup failed", exc_info=True)
        return None
    value = section.get(f"default_model_{backend_name}")
    if isinstance(value, str) and value.strip():
        return value
    return None
