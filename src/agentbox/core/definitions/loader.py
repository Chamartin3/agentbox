"""Load agent definitions from the project volume.

Four sources, merged in priority order (later wins, with a warning):

1. **agents/<name>/agent.toml** — legacy directory form (backwards compat).
2. **agents.d/*.md** — markdown files with YAML frontmatter.
3. **agents.d/*.toml** — standalone TOML files.
4. **Inline** — ``[[agents]]`` blocks in ``manifest.toml`` (highest priority).

Every agent returned by ``load()`` carries ``source_path`` and
``source_format`` so the writer can dispatch to the correct format.
"""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path

from agentbox.core.data.manifest import (
    AgentDef,
    AgentSource,
    ProjectManifest,
    WorkspaceDef,
)
from agentbox.core.definitions.agents_dir import _load_legacy_dir_agent, scan_agents_dir

logger = logging.getLogger(__name__)


def _merge_agent(
    merged: dict[str, AgentDef],
    agent: AgentDef,
    source_label: str,
) -> None:
    """Add ``agent`` to ``merged``, warning on ID collision.

    Later insertions win (overwrite).
    """
    existing = merged.get(agent.id)
    if existing is not None:
        logger.warning(
            "agent id=%r collision: %s overrides %s (source=%s)",
            agent.id,
            source_label,
            _source_label(existing),
            agent.source_format.value if agent.source_format else "?",
        )
    merged[agent.id] = agent


def _source_label(agent: AgentDef) -> str:
    if agent.source_path:
        return str(agent.source_path)
    if agent.source_format:
        return agent.source_format.value
    return "programmatic"


class DefinitionLoader:
    """Loads agent definitions from ``manifest.toml`` + ``agents.d/`` + legacy ``agents/``."""

    def __init__(self, project_root: Path):
        self.project_root = project_root

    @property
    def manifest_path(self) -> Path:
        # New canonical name (Plan 08 container layout).
        new = self.project_root / "manifest.toml"
        if new.exists():
            return new
        return self.project_root / "agentbox.toml"

    @property
    def agents_d_path(self) -> Path:
        return self.project_root / "agents.d"

    @property
    def legacy_agents_path(self) -> Path:
        return self.project_root / "agents"

    def load(self) -> ProjectManifest:
        manifest = self._load_toml()
        merged: dict[str, AgentDef] = {}

        # 1. Legacy agents/<name>/agent.toml (lowest priority)
        legacy_dir = self.legacy_agents_path
        if legacy_dir.is_dir():
            for entry in sorted(legacy_dir.iterdir()):
                if not entry.is_dir():
                    continue
                if entry.name.startswith("."):
                    continue
                try:
                    agent = _load_legacy_dir_agent(entry)
                    if agent is not None:
                        merged[agent.id] = agent
                except Exception:
                    logger.exception("legacy agent dir %s: failed to load", entry.name)

        # 2. agents.d/*.toml and agents.d/*.md
        agents_d = self.agents_d_path
        if agents_d.is_dir():
            for a in scan_agents_dir(agents_d):
                _merge_agent(merged, a, f"agents.d/{a.source_path.name}" if a.source_path else "agents.d")

        # 3. Inline [[agents]] (highest priority)
        for a in manifest.agents:
            if a.source_format is None:
                a.source_format = AgentSource.INLINE_TOML
                a.source_path = self.manifest_path
            _merge_agent(merged, a, str(self.manifest_path))

        manifest.agents = list(merged.values())
        return manifest

    def get(self, agent_id: str) -> AgentDef | None:
        for a in self.load().agents:
            if a.id == agent_id:
                return a
        return None

    def get_workspace(self, name: str) -> WorkspaceDef | None:
        for w in self.load().workspaces:
            if w.name == name:
                return w
        return None

    def list_workspaces(self) -> list[WorkspaceDef]:
        return list(self.load().workspaces)

    # ------------------------------------------------------------------
    # TOML loader
    # ------------------------------------------------------------------

    def _load_toml(self) -> ProjectManifest:
        if not self.manifest_path.exists():
            return ProjectManifest()
        with self.manifest_path.open("rb") as f:
            data = tomllib.load(f)
        return ProjectManifest.model_validate(data)
