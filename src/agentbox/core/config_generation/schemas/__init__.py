"""Config generation schemas — Pydantic models for all generated artifacts.

Claude Code (pinned to 2.1.111):
  ClaudeAgentsConfig, ClaudeSettingsConfig, ClaudeMcpConfig, ClaudeUserConfig

OpenCode (pinned to 1.14.48):
  OpenCodeConfig, OpenCodeUserConfig

Agent markdown frontmatter:
  ClaudeAgentMarkdown, OpenCodeAgentMarkdown

Skill packs:
  SkillFrontmatter, SkillFormatter

Model validation:
  validate_claude_model, validate_opencode_model
  CLAUDE_MODELS, OPENCODE_MODELS
"""

from ._model_registry import CLAUDE_MODELS, OPENCODE_MODELS
from .agents import (
    AgentMarkdownBase,
    ClaudeAgentMarkdown,
    OpenCodeAgentMarkdown,
    RunnerBlock,
)
from .claude import (
    ClaudeAgentEntry,
    ClaudeAgentsConfig,
    ClaudeMcpConfig,
    ClaudeMcpServerHttp,
    ClaudeMcpServerStdio,
    ClaudePermissions,
    ClaudeSettingsConfig,
    ClaudeUserConfig,
    validate_claude_model,
)
from .opencode import (
    OpenCodeAgentEntry,
    OpenCodeConfig,
    OpenCodeMcpEntryLocal,
    OpenCodeMcpEntryRemote,
    OpenCodeUserConfig,
    validate_opencode_model,
)
from .skills import SkillFormatter, SkillFrontmatter
from .versions import CLAUDE_CODE_VERSION, OPENCODE_VERSION

__all__ = [
    "CLAUDE_CODE_VERSION",
    "CLAUDE_MODELS",
    "OPENCODE_MODELS",
    "OPENCODE_VERSION",
    "AgentMarkdownBase",
    "ClaudeAgentEntry",
    "ClaudeAgentMarkdown",
    "ClaudeAgentsConfig",
    "ClaudeMcpConfig",
    "ClaudeMcpServerHttp",
    "ClaudeMcpServerStdio",
    "ClaudePermissions",
    "ClaudeSettingsConfig",
    "ClaudeUserConfig",
    "OpenCodeAgentEntry",
    "OpenCodeAgentMarkdown",
    "OpenCodeConfig",
    "OpenCodeMcpEntryLocal",
    "OpenCodeMcpEntryRemote",
    "OpenCodeUserConfig",
    "RunnerBlock",
    "SkillFormatter",
    "SkillFrontmatter",
    "validate_claude_model",
    "validate_opencode_model",
]
