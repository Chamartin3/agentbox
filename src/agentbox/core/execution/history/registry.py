"""Registry for ``ConversationSource`` implementations.

Sources register via the ``agentbox.conversations`` entry-point group in
``pyproject.toml``. The registry is populated lazily on first access.
"""

from __future__ import annotations

from importlib.metadata import entry_points

from agentbox.core.execution.history.base import ConversationSource

_CONVERSATION_CLASSES: dict[str, type[ConversationSource]] | None = None


def _load_sources() -> dict[str, type[ConversationSource]]:
    out: dict[str, type[ConversationSource]] = {}
    for ep in entry_points(group="agentbox.conversations"):
        try:
            cls = ep.load()
        except Exception as exc:
            print(f"agentbox: failed to load conversations:{ep.name}: {exc}")
            continue
        fmt = getattr(cls, "format", None)
        if not isinstance(fmt, str) or not fmt:
            print(
                f"agentbox: WARNING — conversation source {ep.name!r} "
                f"has no 'format' ClassVar; skipping"
            )
            continue
        if fmt in out:
            print(
                f"agentbox: WARNING — duplicate conversation source "
                f"format={fmt!r}; {out[fmt]} overwritten by {cls}"
            )
        out[fmt] = cls
    return out


def get(format: str) -> type[ConversationSource]:
    """Return the ``ConversationSource`` class for *format*.

    Raises ``KeyError`` if no source is registered for that format.
    """
    global _CONVERSATION_CLASSES
    if _CONVERSATION_CLASSES is None:
        _CONVERSATION_CLASSES = _load_sources()
    cls = _CONVERSATION_CLASSES.get(format)
    if cls is None:
        raise KeyError(f"no conversation source registered for format={format!r}")
    return cls


def available_formats() -> list[str]:
    """Return sorted list of registered format strings."""
    global _CONVERSATION_CLASSES
    if _CONVERSATION_CLASSES is None:
        _CONVERSATION_CLASSES = _load_sources()
    return sorted(_CONVERSATION_CLASSES.keys())
