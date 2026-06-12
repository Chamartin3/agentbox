"""Registry for ``DispatchChannel`` implementations.

Channels register via the ``agentbox.dispatch_channels`` entry-point
group in ``pyproject.toml``. The registry is populated lazily on first
access. The historical delivery log table is named
``webhook_deliveries``; that name is retained even though the channel is
now generic, to avoid a costly migration for an internal table.
"""

from __future__ import annotations

from importlib.metadata import entry_points

from agentbox.core.execution.dispatch.channels.base import DispatchChannel

_DISPATCH_CHANNELS: dict[str, type[DispatchChannel]] | None = None


def _load_channels() -> dict[str, type[DispatchChannel]]:
    out: dict[str, type[DispatchChannel]] = {}
    for ep in entry_points(group="agentbox.dispatch_channels"):
        try:
            cls = ep.load()
        except Exception as exc:
            print(f"agentbox: failed to load dispatch_channels:{ep.name}: {exc}")
            continue
        name = getattr(cls, "name", None)
        if not isinstance(name, str) or not name:
            print(
                f"agentbox: WARNING — dispatch channel {ep.name!r} "
                f"has no 'name' ClassVar; skipping"
            )
            continue
        if name in out:
            print(
                f"agentbox: WARNING — duplicate dispatch channel "
                f"name={name!r}; {out[name]} overwritten by {cls}"
            )
        out[name] = cls
    return out


def get_channel(name: str) -> type[DispatchChannel]:
    """Return the ``DispatchChannel`` class for *name*.

    Raises ``KeyError`` if no channel is registered for that name.
    """
    global _DISPATCH_CHANNELS
    if _DISPATCH_CHANNELS is None:
        _DISPATCH_CHANNELS = _load_channels()
    cls = _DISPATCH_CHANNELS.get(name)
    if cls is None:
        raise KeyError(f"no dispatch channel registered for name={name!r}")
    return cls


def available_channels() -> list[str]:
    """Return sorted list of registered channel names."""
    global _DISPATCH_CHANNELS
    if _DISPATCH_CHANNELS is None:
        _DISPATCH_CHANNELS = _load_channels()
    return sorted(_DISPATCH_CHANNELS.keys())


__all__ = ["available_channels", "get_channel"]
