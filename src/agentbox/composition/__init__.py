"""agentbox.composition re-exports agentbox.core.composition for backward compat."""

from __future__ import annotations

from agentbox.core.composition import ComposeResult, compose

__all__ = ["ComposeResult", "compose"]
