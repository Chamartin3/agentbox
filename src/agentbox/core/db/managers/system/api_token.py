"""ApiTokenManager — API credential token CRUD."""
from __future__ import annotations

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.system.api_token import ApiToken


class ApiTokenManager(Manager[ApiToken]):
    """Manager for the ``api_tokens`` table."""
    model = ApiToken
