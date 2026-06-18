"""Base abstractions for agentbox.core.db — internal machinery, not public.

The only public symbols in this package are ``Entity`` (subclassed by every
model) and ``Manager`` (subclassed by every manager). Everything else
(metadata, engine, manager base) is internal.
"""
from __future__ import annotations

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.base.model import Entity

__all__ = ["Entity", "Manager"]
