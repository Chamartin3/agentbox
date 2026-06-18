"""HostEnvProfileManager — host environment profile CRUD."""
from __future__ import annotations

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.system.host_env_profile import HostEnvProfile


class HostEnvProfileManager(Manager[HostEnvProfile]):
    """Manager for the ``host_env_profiles`` table."""
    model = HostEnvProfile
