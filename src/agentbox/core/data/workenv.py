"""Engine-agnostic value types for workspace configuration and generation.

Relocated from ``workspaces/generation/config.py``,
``workspaces/generation/payload.py``, and the ``Recipe`` class from
``workspaces/generation/recipe.py`` so that ``engines.backends`` can import
them without creating a cycle through ``workspaces.generation``.
"""

from __future__ import annotations
from typing import Any, NotRequired, TypedDict

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from agentbox.core.data.rows import PermissionFileEntry, ResourceBlobRow

import yaml


# ── Config types ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ResourceRef:
    """Reference to a resource — id-only, resolved at render time."""

    id: str


@dataclass(frozen=True)
class AgentRef:
    """Reference to an agent (main or subagent) with its role in the workspace.

    ``description``/``prompt``/``tools`` carry the engine-config payload that
    backends need to build their agent tables (Claude ``claude_agents.json``,
    OpenCode ``opencode.json``). ``tools`` are *resolved* MCP tool names
    (e.g. ``mcp__mcp__foo_get``) — the same shape the legacy
    ``AgentDiscovery.discover_mcp_agents`` produced as ``mcp_tools``.
    """

    id: str
    role: str = "subagent"  # "main" | "subagent"
    description: str = ""
    prompt: str = ""
    tools: list[str] = field(default_factory=list)


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
class WorkspaceConfig:
    """Engine-agnostic workspace configuration.

    This is the primordial input to config-file generation.  It carries
    references (not resolved content) — resolution happens in the
    generator at render time.
    """

    name: str
    description: str = ""
    # Raw env-doc body text, placed verbatim into the engine's instruction
    # file (CLAUDE.md / AGENTS.md) by the recipe. ResourceRef = id-only ref.
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
                raise ValueError("WorkspaceConfig agent ref missing id")
            if agent.id in seen_agent_ids:
                raise ValueError(f"Duplicate agent id in WorkspaceConfig: {agent.id}")
            seen_agent_ids.add(agent.id)

        seen_resource_ids: set[str] = set()
        for resource in self.resources:
            if not resource.id:
                raise ValueError("WorkspaceConfig resource ref missing id")
            if resource.id in seen_resource_ids:
                raise ValueError(
                    f"Duplicate resource id in WorkspaceConfig: {resource.id}"
                )
            seen_resource_ids.add(resource.id)

        for skill in self.skills:
            if not skill.id:
                raise ValueError("WorkspaceConfig skill ref missing id")

    def to_yaml(self) -> str:
        """Serialize to a YAML string (identity round-trip with ``from_yaml``)."""
        return yaml.dump(self._to_dict(), sort_keys=False, default_flow_style=False)

    @classmethod
    def from_yaml(cls, text: str) -> WorkspaceConfig:
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
                {
                    "id": a.id,
                    "role": a.role,
                    "description": a.description,
                    "prompt": a.prompt,
                    "tools": a.tools,
                }
                for a in self.agents
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
    def _from_dict(cls, data: dict[str, Any]) -> WorkspaceConfig:
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
                AgentRef(
                    id=a["id"],
                    role=a.get("role", "subagent"),
                    description=a.get("description", ""),
                    prompt=a.get("prompt", ""),
                    tools=list(a.get("tools", [])),
                )
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


# ── Payload types ─────────────────────────────────────────────────────────────


class Role(str, Enum):
    """Role of an output item — determines its file path via recipe layout."""

    context = "context"
    engine_config = "engine_config"
    subagent = "subagent"
    skill = "skill"
    mcp_config = "mcp_config"
    permissions = "permissions"


@dataclass
class Item:
    """A single output unit — role, name, and resolved content."""

    role: Role
    name: str
    content: str


@dataclass(frozen=True)
class WrittenItem:
    """Metadata for one item the generator wrote to disk.

    Lets callers derive snapshot/provenance entries from what was actually
    written, instead of a parallel hardcoded write path.
    """

    role: str  # Role value, e.g. "context"
    file: str  # relative layout path, e.g. "CLAUDE.md"
    bytes: int


@dataclass
class RenderedDir:
    """Result of a render operation."""

    target_dir: Path
    written_paths: list[Path] = field(default_factory=list)
    items: list[WrittenItem] = field(default_factory=list)


@dataclass(frozen=True)
class RenderedFile:
    """One rendered file as an in-memory preview (no disk residue)."""

    rel_path: Path
    content: str


# ── Recipe value type ─────────────────────────────────────────────────────────


# ── Composition / Blueprint contracts ────────────────────────────────────────


class SourceMetadata(TypedDict):
    """Metadata carried by imported resource versions, used by materialize.py."""

    filename: NotRequired[str]
    host_path: NotRequired[str]


@dataclass(frozen=True)
class ResolvedBinding:
    """A fully resolved workspace file binding, ready for materialization."""

    binding_id: str
    resource_id: str
    version_id: str
    content_hash: str
    type: str
    slug: str
    display_name: str
    target_path: str | None
    materialize_mode: str
    on_conflict: str
    blobs: tuple[ResourceBlobRow, ...]
    skill_meta: None = None
    source_metadata: SourceMetadata | None = None


@dataclass(frozen=True)
class ResolvedSubagent:
    """A fully resolved workspace subagent, ready for generation."""

    workspace_id: str
    agent_id: str
    alias: str
    description: str | None
    prompt_content: str


class EffectivePermissionsOverlay(TypedDict):
    """Optional permission overrides resolved for a workspace run.

    Mirrors the keys built in ``prep.load_workspace_permissions``.
    """

    allowed_builtin_tools: NotRequired[list[str]]
    files: NotRequired[list[PermissionFileEntry]]
    max_tokens: NotRequired[int]
    allow_file_write: NotRequired[bool]
    allow_network: NotRequired[bool]


@dataclass(frozen=True)
class WorkspaceBlueprint:
    """Immutable contract between ``WorkspaceComposer`` and ``WorkspaceRenderer``.

    Produced by ``compose()``, consumed by ``render()``.  Never mutated
    after creation.
    """

    workspace_id: str
    config: WorkspaceConfig
    recipes: tuple[Recipe, ...]
    bindings: tuple[ResolvedBinding, ...]
    subagents: tuple[ResolvedSubagent, ...]
    env_doc_body: str | None
    env_doc_version_id: str | None
    permissions: EffectivePermissionsOverlay | None
    secret_keys: tuple[str, ...]


@dataclass(frozen=True)
class MaterializeOutcome:
    """Outcome of materializing one workspace file binding into a workdir."""

    binding_id: str
    resource_id: str
    version_id: str
    content_hash: str
    target_path: str
    files_written: int
    mode: str
    skipped: bool = False
    skipped_reason: str | None = None


@dataclass(frozen=True)
class Recipe:
    """Engine-specific workspace layout.

    Loaded from a backend's ``recipe.yaml`` file.
    """

    engine: str
    recipe_dir: Path
    layout: dict[str, str] = field(default_factory=dict)
    serialization: dict[str, str] = field(default_factory=dict)
    templates: dict[str, str] = field(default_factory=dict)

    def resolve_layout(self, role: str, **fmt_kwargs: str) -> str:
        """Resolve a layout path for *role*, formatting with *fmt_kwargs*."""
        pattern = self.layout.get(role, "")
        return pattern.format(**fmt_kwargs)

    def resolve_template(self, role: str) -> str | None:
        """Return the template content for *role*, or None."""
        tmpl_path = self.templates.get(role)
        if tmpl_path is None:
            return None
        full_path = self.recipe_dir / tmpl_path
        if not full_path.is_file():
            return None
        return full_path.read_text(encoding="utf-8")
