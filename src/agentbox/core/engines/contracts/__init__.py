"""Backend framework contracts.

The ABC and value types that define what a backend *is* — separated from
``engines/backends/``, which is the pure catalog of concrete backend
implementations. Catalog members and the executor both implement against
these contracts.
"""

from agentbox.core.engines.contracts.base import BackendAdapter
from agentbox.core.engines.contracts.rendered import RenderedConfig

__all__ = ["BackendAdapter", "RenderedConfig"]
