"""WorkenvTemplateManager — work environment template CRUD."""
from __future__ import annotations

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.workspaces.template import WorkenvTemplate


class WorkenvTemplateManager(Manager[WorkenvTemplate]):
    """Manager for the ``workenv_templates`` table."""
    model = WorkenvTemplate
