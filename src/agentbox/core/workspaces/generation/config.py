"""WorkenvConfig — engine-agnostic, DB-decoupled value type for workspace generation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import yaml


@dataclass(frozen=True)
class ResourceRef:
    """Reference to a resource — id-only, resolved at render time."""

    id: str


@dataclass(frozen=True)
class AgentRef:
    """Reference to an agent (main or subagent) with its role in the workspace."""

    id: str
    role: str = "subagent"  # "main" | "subagent"


@dataclass(frozen=True)
class McpRef:
    """Reference to an MCP server with per-server tool overrides."""

    name: str
    config: dict[str, Any] = field(default_factory=dict)
    disabled_tools: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Permissions:
    """Opaque permissions dict — consumed by the generator at render time."""

    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkenvConfig:
    """Engine-agnostic workspace configuration.

    This is the primordial input to config-file generation.  It carries
    references (not resolved content) — resolution happens in the
    generator at render time.
    """

    name: str
    description: str = ""
    env_doc: str | ResourceRef | None = None
    agents: list[AgentRef] = field(default_factory=list)
    resources: list[ResourceRef] = field(default_factory=list)
    skills: list[ResourceRef] = field(default_factory=list)
    mcp_servers: list[McpRef] = field(default_factory=list)
    permissions: Permissions = field(default_factory=Permissions)
    env: Mapping[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        """Validate referential consistency — no DB session required."""
        seen_agent_ids: set[str] = set()
        for agent in self.agents:
            if not agent.id:
                raise ValueError("WorkenvConfig agent ref missing id")
            if agent.id in seen_agent_ids:
                raise ValueError(f"Duplicate agent id in WorkenvConfig: {agent.id}")
            seen_agent_ids.add(agent.id)

        seen_resource_ids: set[str] = set()
        for resource in self.resources:
            if not resource.id:
                raise ValueError("WorkenvConfig resource ref missing id")
            if resource.id in seen_resource_ids:
                raise ValueError(
                    f"Duplicate resource id in WorkenvConfig: {resource.id}"
                )
            seen_resource_ids.add(resource.id)

        for skill in self.skills:
            if not skill.id:
                raise ValueError("WorkenvConfig skill ref missing id")

    def to_yaml(self) -> str:
        """Serialize to a YAML string (identity round-trip with ``from_yaml``)."""
        return yaml.dump(self._to_dict(), sort_keys=False, default_flow_style=False)

    @classmethod
    def from_yaml(cls, text: str) -> WorkenvConfig:
        """Deserialize from a YAML string produced by ``to_yaml()``."""
        data = yaml.safe_load(text) or {}
        return cls._from_dict(data)

    def _to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "env_doc": (
                self.env_doc
                if isinstance(self.env_doc, str) or self.env_doc is None
                else {"__ref__": "resource", "id": self.env_doc.id}
            ),
            "agents": [
                {"id": a.id, "role": a.role} for a in self.agents
            ],
            "resources": [{"id": r.id} for r in self.resources],
            "skills": [{"id": s.id} for s in self.skills],
            "mcp_servers": [
                {
                    "name": m.name,
                    "config": m.config,
                    "disabled_tools": m.disabled_tools,
                }
                for m in self.mcp_servers
            ],
            "permissions": self.permissions.data,
            "env": dict(self.env) if self.env else {},
        }

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> WorkenvConfig:
        raw_env_doc = data.get("env_doc")
        env_doc: str | ResourceRef | None = None
        if isinstance(raw_env_doc, dict) and raw_env_doc.get("__ref__") == "resource":
            env_doc = ResourceRef(id=raw_env_doc["id"])
        elif isinstance(raw_env_doc, str):
            env_doc = raw_env_doc

        permissions_data = data.get("permissions") or {}
        if isinstance(permissions_data, Permissions):
            permissions = permissions_data
        else:
            permissions = Permissions(data=dict(permissions_data))

        return cls(
            name=data["name"],
            description=data.get("description", ""),
            env_doc=env_doc,
            agents=[
                AgentRef(id=a["id"], role=a.get("role", "subagent"))
                for a in data.get("agents", [])
            ],
            resources=[ResourceRef(id=r["id"]) for r in data.get("resources", [])],
            skills=[ResourceRef(id=s["id"]) for s in data.get("skills", [])],
            mcp_servers=[
                McpRef(
                    name=m["name"],
                    config=m.get("config", {}),
                    disabled_tools=m.get("disabled_tools", []),
                )
                for m in data.get("mcp_servers", [])
            ],
            permissions=permissions,
            env=dict(data.get("env", {})),
        )
