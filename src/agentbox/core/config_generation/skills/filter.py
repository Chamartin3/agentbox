"""Filter workspace skills by backend compatibility."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentbox.core.skills import SkillPack


@dataclass(frozen=True)
class ParsedSkillFrontmatter:
    """Minimal parsed frontmatter from a SKILL.md file."""

    runners: list[str] | None = None


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_frontmatter(content: str) -> ParsedSkillFrontmatter:
    """Extract the runners field from YAML frontmatter if present."""
    m = _FRONTMATTER_RE.search(content)
    if not m:
        return ParsedSkillFrontmatter(runners=None)
    yaml_block = m.group(1)
    runners: list[str] | None = None
    for line in yaml_block.splitlines():
        line = line.strip()
        if line.startswith("runners:"):
            # runners: [claude_code, opencode]
            rest = line[len("runners:") :].strip()
            if rest.startswith("[") and rest.endswith("]"):
                raw = rest[1:-1]
                runners = [s.strip().strip('"').strip("'") for s in raw.split(",")]
            elif rest:
                # Could be multi-line list; skip for now
                pass
    return ParsedSkillFrontmatter(runners=runners)


def filter_skills_for_backend(
    skills: list[SkillPack],
    backend: str,
) -> list[SkillPack]:
    """Return skills applicable to ``backend``.

    A skill is applicable if its frontmatter does not declare ``runners``
    or if ``backend`` is in the declared list.
    """
    applicable: list[SkillPack] = []
    for skill in skills:
        fm = _parse_frontmatter(skill.content)
        if fm.runners is None or backend in fm.runners:
            applicable.append(skill)
    return applicable
