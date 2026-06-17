"""Pydantic models for OpenCode configuration files.

Covers every JSON artifact that agentbox generates or ships as a default:
  - opencode.json       (full OpenCode workspace config)
  - user-config.json    (UI preferences seeded into the opencode volume)

Pinned to OpenCode 1.14.48.
Schema ref: https://opencode.ai/config.json
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

OPENCODE_SCHEMA_URL = "https://opencode.ai/config.json"

Permission = Literal["allow", "ask"]


# ---------------------------------------------------------------------------
# MCP server entries
# ---------------------------------------------------------------------------


class OpenCodeMcpEntryRemote(BaseModel):
    type: Literal["remote"] = "remote"
    url: str
    enabled: bool = True

    model_config = {"extra": "allow"}


class OpenCodeMcpEntryLocal(BaseModel):
    type: Literal["local"] = "local"
    command: list[str]
    enabled: bool = True

    model_config = {"extra": "allow"}


OpenCodeMcpEntry = OpenCodeMcpEntryRemote | OpenCodeMcpEntryLocal


# ---------------------------------------------------------------------------
# Agent entry
# ---------------------------------------------------------------------------


class OpenCodeAgentEntry(BaseModel):
    """One entry in opencode.json ``agent`` map."""

    description: str = ""
    prompt: str = ""
    tools: dict[str, bool] = Field(default_factory=dict)
    permission: dict[str, Permission] = Field(default_factory=dict)
    disable: bool = False
    model: str | None = None

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# Top-level opencode.json
# ---------------------------------------------------------------------------


class OpenCodeConfig(BaseModel):
    """Full opencode.json workspace configuration.

    Pinned to OpenCode 1.14.48 / schema https://opencode.ai/config.json
    """

    schema_url: str = Field(
        default=OPENCODE_SCHEMA_URL, alias="$schema", serialization_alias="$schema"
    )
    theme: str = "dracula"
    tools: dict[str, bool] = Field(default_factory=dict)
    permission: dict[str, Permission] = Field(default_factory=dict)
    agent: dict[str, OpenCodeAgentEntry] = Field(default_factory=dict)
    mcp: dict[str, OpenCodeMcpEntryRemote | OpenCodeMcpEntryLocal] = Field(
        default_factory=dict
    )

    model_config = {"extra": "allow", "populate_by_name": True}

    @model_validator(mode="after")
    def global_permission_has_wildcard(self) -> OpenCodeConfig:
        if self.permission and "*" not in self.permission:
            raise ValueError(
                "opencode.json global permission map must contain a '*' fallback entry"
            )
        return self


# ---------------------------------------------------------------------------
# user-config.json (seeded into the agentbox-opencode volume)
# ---------------------------------------------------------------------------


class OpenCodeUserConfig(BaseModel):
    """OpenCode UI preferences written to the opencode data volume.

    Pinned to OpenCode 1.14.48.
    """

    theme: str = "dracula"
    autoshare: bool = False

    model_config = {"extra": "allow"}
