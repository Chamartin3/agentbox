"""Engine adapters, rendering, and post-render hooks.

**Import from this package, not its submodules.**
"""

from agentbox.core.engines.backends.base import BackendAdapter, RenderedConfig
from agentbox.core.engines.backends import get_backend, list_backends

__all__ = [
    "BackendAdapter",
    "RenderedConfig",
    "get_backend",
    "list_backends",
]
