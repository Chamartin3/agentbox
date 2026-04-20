"""Skill pack discovery for workspaces.

A skill pack is a directory containing a SKILL.md file. We look in the
runner-native locations (`.claude/skills/`, `.opencode/skills/`) and the
legacy plain `skills/` directory. Skill names dedupe across roots —
first-match wins, with .claude/skills/ taking precedence.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Where to look for skill packs inside a workspace, in priority order.
_SKILL_ROOTS: tuple[str, ...] = (".claude/skills", ".opencode/skills", "skills")


@dataclass
class SkillPack:
    name: str
    path: Path
    content: str


def skill_roots(workspace_path: Path) -> list[Path]:
    """Return every existing skill-pack root inside the workspace."""
    return [workspace_path / rel for rel in _SKILL_ROOTS
            if (workspace_path / rel).is_dir()]


def discover_skills(workspace_path: Path) -> list[SkillPack]:
    """Discover all skill packs across the runner-native skill directories."""
    packs: list[SkillPack] = []
    seen: set[str] = set()
    for root in skill_roots(workspace_path):
        for skill_dir in root.iterdir():
            if not skill_dir.is_dir() or skill_dir.name in seen:
                continue
            skill_md = skill_dir / "SKILL.md"
            if skill_md.is_file():
                seen.add(skill_dir.name)
                packs.append(
                    SkillPack(
                        name=skill_dir.name,
                        path=skill_dir,
                        content=skill_md.read_text(encoding="utf-8"),
                    )
                )
    return sorted(packs, key=lambda s: s.name)


def find_skill(workspace_path: Path, skill_name: str) -> Path | None:
    """Locate a single skill's SKILL.md across runner-native roots."""
    for root in skill_roots(workspace_path):
        candidate = root / skill_name / "SKILL.md"
        if candidate.is_file():
            return candidate
    return None


def build_skills_prompt(skills: list[SkillPack]) -> str:
    """Build a prompt fragment from discovered skills."""
    if not skills:
        return ""
    lines = ["# Skills available to you\n"]
    for skill in skills:
        lines.append(f"\n## {skill.name}\n")
        lines.append(skill.content)
    return "\n".join(lines)
