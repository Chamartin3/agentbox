"""Service layer for resource and workspace bindings (backward-compatible re-exports).

Deprecated — use the subpackages directly:
- ``agentbox.core.service.resources.bindings`` — prompt + workspace file bindings
- ``agentbox.core.service.workspaces.bindings`` — subagents + skill bindings
"""

from __future__ import annotations

from agentbox.core.service.resources.bindings import (
    AgentVersionMissing,
    BindingError,
    PreviewError,
    PromptMode,
    PromptSlot,
    dry_run_workspace_resources,
    list_prompt_resources,
    list_workspace_resources,
    preview_modes,
    preview_prompt,
    replace_prompt_resources,
    replace_workspace_resources,
)
from agentbox.core.service.workspaces.bindings import (
    list_workspace_skill_bindings,
    list_workspace_subagents,
    replace_workspace_skill_bindings,
    replace_workspace_subagents,
)

__all__ = [
    "BindingError",
    "AgentVersionMissing",
    "PreviewError",
    "PromptMode",
    "PromptSlot",
    "list_prompt_resources",
    "replace_prompt_resources",
    "preview_prompt",
    "list_workspace_resources",
    "replace_workspace_resources",
    "dry_run_workspace_resources",
    "preview_modes",
    "list_workspace_subagents",
    "replace_workspace_subagents",
    "list_workspace_skill_bindings",
    "replace_workspace_skill_bindings",
]
