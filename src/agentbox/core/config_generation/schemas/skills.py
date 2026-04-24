"""Pydantic schema for SKILL.md frontmatter.

A SKILL.md file is a markdown document with YAML frontmatter that describes
a reusable skill pack. Both Claude Code and OpenCode discover these files.

Discovery paths (highest → lowest priority):
  .claude/skills/<name>/SKILL.md
  .opencode/skills/<name>/SKILL.md
  skills/<name>/SKILL.md   (legacy)

Frontmatter format:
  ---
  name: my-skill
  description: What this skill teaches the agent.
  version: "1.0.0"
  tags: [python, fastapi]
  formatter:
    style: bullet      # bullet | prose | numbered
    max_items: 10
    include_examples: true
  ---
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SkillFormatter(BaseModel):
    """Controls how skill content is rendered into the agent prompt."""

    style: Literal["bullet", "prose", "numbered"] = "prose"
    max_items: int | None = Field(default=None, ge=1)
    include_examples: bool = True
    header_level: int = Field(default=2, ge=1, le=6)

    model_config = {"extra": "allow"}


class SkillFrontmatter(BaseModel):
    """YAML frontmatter block for a SKILL.md file.

    The markdown body below the frontmatter becomes the skill content
    injected into agent prompts.
    """

    name: str = Field(description="Unique skill identifier, used in tool/prompt refs.")
    description: str = Field(
        description="One-line summary shown in skill listings and agent UIs."
    )
    version: str | None = Field(
        default=None,
        description="Semantic version string (e.g. '1.2.0'). Optional.",
        pattern=r"^\d+\.\d+(\.\d+)?$",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Free-form tags for filtering/discovery.",
    )
    formatter: SkillFormatter = Field(
        default_factory=SkillFormatter,
        description="Controls how skill content is formatted when injected into prompts.",
    )
    runners: list[Literal["claude_code", "opencode", "pydantic_ai"]] | None = Field(
        default=None,
        description="Runners this skill applies to. None means all runners.",
    )

    model_config = {"extra": "allow"}
