"""agentbox.composition re-exports agentbox.core.composition for backward compat."""

from __future__ import annotations

from agentbox.core.composition import ComposeResult, compose, compose_from_source

__all__ = ["ComposeResult", "compose", "compose_from_source"]
