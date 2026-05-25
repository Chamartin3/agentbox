"""``token`` backend package — unified in-process pydantic-ai adapter.

This package was extracted from a single 993-LOC ``token.py`` module
during the Phase-5 backend refactor. The public surface is unchanged:

* The entry-point ``token = agentbox.core.run.backends.token:TokenBackend``
  in :file:`pyproject.toml` continues to resolve here.
* Helpers and module-level names imported by callers / tests
  (``_json_schema_to_pydantic_model``, ``importlib``, ``TokenDeps``,
  ``_RefSection``, etc.) are re-exported below so existing
  ``from agentbox.core.run.backends.token import X`` statements keep
  working.

The submodule layout:

* :mod:`._backend` — the :class:`TokenBackend` adapter.
* :mod:`._stream` — pydantic-ai message-history adaptation, error
  formatting, and the ``TokenDeps`` carrier.
* :mod:`._schema` — loose JSON-Schema → pydantic fallback converter.
* :mod:`._usage` — usage-object normalisation across pydantic-ai
  versions.

Imported at module scope so ``patch("…token.importlib.import_module")``
in the legacy provider-routing tests continues to bind to the same
``importlib`` object the backend actually uses.
"""

from __future__ import annotations

import importlib

from agentbox.core.run.backends.token._backend import TokenBackend
from agentbox.core.run.backends.token._schema import _json_schema_to_pydantic_model
from agentbox.core.run.backends.token._stream import (
    _RefSection,
    TokenDeps,
    _emit_message_history,
    _format_provider_error,
    _iter_message_history_events,
    _part_kind,
    _stringify_excerpt,
)
from agentbox.core.run.backends.token._usage import extract_usage

__all__ = [
    "TokenBackend",
    "TokenDeps",
    "_RefSection",
    "_emit_message_history",
    "_format_provider_error",
    "_iter_message_history_events",
    "_json_schema_to_pydantic_model",
    "_part_kind",
    "_stringify_excerpt",
    "extract_usage",
    "importlib",
]
