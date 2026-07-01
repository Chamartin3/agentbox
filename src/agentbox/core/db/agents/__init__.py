"""Agent-scoped data layer.

The legacy per-domain CRUD mixins (AgentConfigEventsMixin, AgentSyncMixin,
AgentToolGrantsMixin, PromptVersionsMixin, AgentVersionsMixin) were removed
with SessionStore. All agent CRUD now lives in the managers under
``core/db/managers/agents/`` and is reached via the facade
``from agentbox.core.db import <Manager>``.
"""
