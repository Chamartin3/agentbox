"""Resources mixin — composed into SessionStore."""

from agentbox.core.data.resources.crud._repo import ResourceCrudMixin
from agentbox.core.data.resources.crud._versions import ResourceVersionMixin
from agentbox.core.data.resources.crud._blobs import ResourceBlobMixin

__all__ = [
    "ResourcesMixin",
]


class ResourcesMixin(
    ResourceCrudMixin,
    ResourceVersionMixin,
    ResourceBlobMixin,
):
    """Versioned resource repository. Requires ``self.engine: Engine``.
    
    Composed from sub-mixins. See individual modules for method docs.
    """
