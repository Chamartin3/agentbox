"""HostEnvCallLogManager — host env call audit log CRUD."""
from __future__ import annotations

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.system.host_env_call import HostEnvCallLog


class HostEnvCallLogManager(Manager[HostEnvCallLog]):
    """Manager for the ``host_env_call_log`` table."""
    model = HostEnvCallLog
