"""Manifest editor — round-trips agentbox.toml through tomlkit.

Preserves comments and formatting; rejects patches that would produce
an invalid AgentDef. Writes are atomic (tmp + rename).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomlkit
from tomlkit.items import AoT, Table

from .loader import ProjectManifest
from .models import AgentDef


# Fields that may be edited via PATCH /manifest/agents/{id}.
_AGENT_PATCHABLE = {
    "description",
    "session_mode",
    "workspace",
    "tags",
    "claude_agent",
    "headless",
    "tools",
    "prompt",
    "prompt_path",
}
_RUNNER_PATCHABLE = {
    "kind",
    "model",
    "mcp_config_path",
    "agents_config_path",
    "settings_path",
    "config_path",
    "allowed_tools",
    "extra_args",
    "timeout_seconds",
    "command",
}


@dataclass
class PatchError(Exception):
    code: str
    detail: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.code}: {self.detail}"


class ManifestWriter:
    def __init__(self, project_root: Path):
        self.project_root = project_root

    @property
    def path(self) -> Path:
        return self.project_root / "agentbox.toml"

    def read_text(self) -> str:
        if not self.path.exists():
            return ""
        return self.path.read_text(encoding="utf-8")

    def read_parsed(self) -> ProjectManifest:
        if not self.path.exists():
            return ProjectManifest()
        data = tomlkit.parse(self.read_text())
        return ProjectManifest.model_validate(_to_plain(data))

    def patch_agent(self, agent_id: str, patch: dict[str, Any]) -> AgentDef:
        """Apply a patch to one agent. Returns the updated AgentDef.

        Raises PatchError on unknown agent, forbidden field, or validation failure.
        """
        if not self.path.exists():
            raise PatchError("no_manifest", "agentbox.toml not found at project root")

        doc = tomlkit.parse(self.read_text())
        agents = doc.get("agents")
        if not isinstance(agents, AoT):
            raise PatchError("no_agents", "agentbox.toml has no [[agents]] entries")

        target_table = _find_agent_table(agents, agent_id)
        if target_table is None:
            raise PatchError("unknown_agent", f"no agent with id={agent_id!r}")

        _apply_patch(target_table, patch)

        # Validate the entire manifest by re-parsing through pydantic.
        # If it fails, do NOT write — surface the validation error.
        try:
            parsed = ProjectManifest.model_validate(_to_plain(doc))
        except Exception as exc:  # noqa: BLE001
            raise PatchError("validation_failed", str(exc)) from exc

        # Atomic write.
        new_text = tomlkit.dumps(doc)
        _atomic_write(self.path, new_text)

        for a in parsed.agents:
            if a.id == agent_id:
                return a
        raise PatchError("post_validate", "agent missing after re-parse")


def _find_agent_table(agents: AoT, agent_id: str) -> Table | None:
    for entry in agents:
        if isinstance(entry, Table) and entry.get("id") == agent_id:
            return entry
    return None


def _apply_patch(table: Table, patch: dict[str, Any]) -> None:
    runner_patch = patch.get("runner") or {}
    for k, v in patch.items():
        if k == "runner":
            continue
        if k == "id":
            raise PatchError("forbidden_field", "cannot change agent id")
        if k not in _AGENT_PATCHABLE:
            raise PatchError("forbidden_field", f"field {k!r} is not editable")
        if v is None:
            if k in table:
                del table[k]
        else:
            table[k] = v

    if runner_patch:
        runner_tbl = table.get("runner")
        if not isinstance(runner_tbl, Table):
            raise PatchError("no_runner", "agent has no [agents.runner] table")
        for k, v in runner_patch.items():
            if k not in _RUNNER_PATCHABLE:
                raise PatchError("forbidden_field", f"runner.{k} is not editable")
            if v is None:
                if k in runner_tbl:
                    del runner_tbl[k]
            else:
                runner_tbl[k] = v


def _to_plain(doc: Any) -> Any:
    """Convert a tomlkit document to plain dict/list for pydantic validation."""
    if isinstance(doc, dict):
        return {k: _to_plain(v) for k, v in doc.items()}
    if isinstance(doc, list):
        return [_to_plain(v) for v in doc]
    # tomlkit scalar items behave like their underlying Python types; unwrap.
    if hasattr(doc, "unwrap"):
        return doc.unwrap()
    return doc


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
