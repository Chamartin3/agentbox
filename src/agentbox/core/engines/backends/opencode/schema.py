"""Typed structure of ``opencode.json``.

The OpenCode backend owns the shape of its own config file. Building the
blob from these models (instead of hand-rolled dicts) keeps the contract
explicit and gives us ``model_json_schema()`` for free.

Schema ref: https://opencode.ai/config.json
"""

from __future__ import annotations

from pydantic import BaseModel, Field

OPENCODE_SCHEMA_URL = "https://opencode.ai/config.json"


class McpRemote(BaseModel):
    type: str = "remote"
    url: str
    enabled: bool = True


class McpLocal(BaseModel):
    type: str = "local"
    command: list[str]
    enabled: bool = True


class AgentEntry(BaseModel):
    description: str = ""


class OpenCodeConfig(BaseModel):
    """Full ``opencode.json`` workspace config."""

    schema_url: str = Field(
        default=OPENCODE_SCHEMA_URL, alias="$schema", serialization_alias="$schema"
    )
    theme: str = "dracula"
    tools: dict[str, bool] = Field(default_factory=dict)
    permission: dict[str, str] = Field(default_factory=dict)
    agent: dict[str, AgentEntry] = Field(default_factory=dict)
    mcp: dict[str, McpRemote | McpLocal] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}
