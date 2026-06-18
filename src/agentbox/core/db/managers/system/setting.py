"""SettingManager — application settings key-value CRUD."""
from __future__ import annotations

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.system.setting import Setting


class SettingManager(Manager[Setting]):
    """Manager for the ``settings`` table (composite PK section+key)."""
    model = Setting
