"""Workspace skill discovery, materialization, and content access."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from agentbox.config import Settings
from agentbox.core import workspaces as ws
from agentbox.core.data import SessionStore
from agentbox.core.resources.skills import discover_skills, find_skill

from .files import _resolve_agent_or_raise, resolve_workspace_path

__all__ = [
    "generate_skills_by_name",
    "list_skills_by_name",
    "get_skill_content_by_name",
    "list_skills_for_agent",
]


def _generate_skills_dir(skills: list, ws_path: Path, subdir: str) -> Path:
    out_dir = ws_path / subdir / "skills"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for skill in skills:
        skill_dir = out_dir / skill.name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(skill.content, encoding="utf-8")
    return out_dir


def generate_skills_by_name(
    name: str,
    *,
    store: SessionStore,
    settings: Settings,
    loader: Any = None,
) -> dict:
    ws_path, _ = resolve_workspace_path(
        name, store=store, settings=settings, loader=loader
    )
    skills = discover_skills(ws_path)
    claude_dir = _generate_skills_dir(skills, ws_path, ".claude")
    opencode_dir = _generate_skills_dir(skills, ws_path, ".opencode")
    return {
        "workspace": name,
        "skills_count": len(skills),
        "generated": {
            "claude_skills": str(claude_dir),
            "opencode_skills": str(opencode_dir),
        },
    }


def list_skills_by_name(
    name: str,
    *,
    store: SessionStore,
    settings: Settings,
    loader: Any = None,
) -> dict:
    ws_path, _ = resolve_workspace_path(
        name, store=store, settings=settings, loader=loader
    )
    skills = discover_skills(ws_path)
    return {
        "workspace": name,
        "workspace_path": str(ws_path),
        "skills": [
            {
                "name": s.name,
                "path": str(s.path.relative_to(ws_path)),
                "size": len(s.content.encode("utf-8")),
            }
            for s in skills
        ],
    }


def get_skill_content_by_name(
    name: str,
    skill_name: str,
    *,
    store: SessionStore,
    settings: Settings,
    loader: Any = None,
) -> dict | None:
    ws_path, _ = resolve_workspace_path(
        name, store=store, settings=settings, loader=loader
    )
    skill_md = find_skill(ws_path, skill_name)
    if skill_md is None:
        return None
    return {
        "workspace": name,
        "skill": skill_name,
        "path": str(skill_md.relative_to(ws_path)),
        "content": skill_md.read_text(encoding="utf-8"),
    }


def list_skills_for_agent(
    agent_id: str,
    *,
    store: SessionStore,
    settings: Settings,
    loader: Any,
) -> dict:
    agent = _resolve_agent_or_raise(agent_id, loader=loader)
    workspace_path, _ = ws.resolve_path(agent, settings, store)
    skills = discover_skills(workspace_path)
    return {
        "agent_id": agent_id,
        "workspace": str(workspace_path),
        "skills": [
            {
                "name": s.name,
                "path": str(s.path.relative_to(workspace_path)),
                "size": len(s.content.encode("utf-8")),
            }
            for s in skills
        ],
    }
