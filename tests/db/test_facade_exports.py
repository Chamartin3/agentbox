"""Regression guard for the ``agentbox.core.db`` façade.

The façade exports **managers only**. If a name disappears from ``__all__``
(or stops being importable), call sites break.
"""

from __future__ import annotations

import agentbox.core.db as data


EXPECTED_EXPORTS: frozenset[str] = frozenset(
    {
        # runs managers
        "RunCommentManager",
        "RunManager",
        "RunPromptManager",
        "SessionManager",
        "UsageManager",
        "WebhookDeliveryManager",
        # agents managers
        "ActiveAgentVersionManager",
        "AgentConfigEventManager",
        "AgentDefManager",
        "AgentManager",
        "AgentMetaManager",
        "AgentRunnerProfileManager",
        "AgentSyncManager",
        "AgentToolGrantManager",
        "AgentVersionCommentManager",
        "AgentVersionFileManager",
        "AgentVersionManager",
        "AgentVersionRatingManager",
        "PromptVersionManager",
        # workspaces managers
        "WorkspaceEnvDocManager",
        "WorkspaceEnvDocVersionManager",
        "WorkspaceHostEnvGrantManager",
        "WorkspaceManager",
        "WorkspaceMcpOverrideManager",
        "WorkspaceMcpPolicyManager",
        "WorkspaceMcpToolOverrideManager",
        "WorkspaceRuntimePermissionManager",
        "WorkspaceSubagentManager",
        # resources managers
        "ActiveResourceVersionManager",
        "AgentPromptResourceBindingManager",
        "ResourceBlobManager",
        "ResourceManager",
        "ResourceVersionManager",
        "SharedResourceManager",
        "WorkspaceFileResourceBindingManager",
        # engines managers
        "RunnerProfileManager",
        # system managers
        "ApiTokenManager",
        "HostEnvCallLogManager",
        "HostEnvProfileManager",
        "McpToolDiscoveryCacheManager",
        "SettingManager",
    }
)


def test_all_matches_expected() -> None:
    actual = frozenset(data.__all__)
    removed = EXPECTED_EXPORTS - actual
    added = actual - EXPECTED_EXPORTS
    assert not removed, f"facade lost exports: {sorted(removed)}"
    assert not added, (
        f"facade gained exports without updating this test: {sorted(added)}"
    )


def test_every_export_is_importable() -> None:
    missing = [name for name in data.__all__ if not hasattr(data, name)]
    assert not missing, f"declared in __all__ but not present on module: {missing}"


def test_session_store_is_gone() -> None:
    assert "SessionStore" not in data.__all__
    assert not hasattr(data, "SessionStore")
