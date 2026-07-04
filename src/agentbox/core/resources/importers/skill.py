"""Skill importer — a HostPathImporter that parses SKILL.md frontmatter.

A "skill" is a folder with a `SKILL.md` entry file. Frontmatter (YAML
between the first two ``---`` markers, or simple ``key: value`` lines
before the first heading) provides ``name`` / ``description`` shown in
listings and used by prompt-embed bindings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from agentbox.core.data.constants import ResourceType
from agentbox.core.resources.importers.base import ImporterContext, ImporterResult
from agentbox.core.resources.importers.host_path import HostPathImporter

ENTRY_FILE = "SKILL.md"
_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_frontmatter(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    m = _FM_RE.match(text)
    if not m:
        return out
    block = m.group(1)
    for line in block.splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        out[k.strip()] = v.strip().strip("'\"")
    return out


@dataclass(frozen=True)
class SkillImporter(HostPathImporter):
    import_source: str = "host_path"

    def run(self, ctx: ImporterContext) -> ImporterResult:
        result = super().run(ctx)
        entry = next((b for b in result.blobs if b[0] == ENTRY_FILE), None)
        if entry is None:
            raise ValueError(
                f"Skill folder {self.root} is missing required entry file {ENTRY_FILE!r}"
            )
        text = entry[3] or entry[1].decode("utf-8", errors="replace")
        fm = _parse_frontmatter(text)
        skill_name = fm.get("name") or self.root.name
        skill_desc = fm.get("description")
        return ImporterResult(
            blobs=result.blobs,
            import_source=result.import_source,
            source_metadata={
                **(result.source_metadata or {}),
                "kind": "skill",
            },
            metadata={
                "skill_name": skill_name,
                "skill_description": skill_desc,
                "entry_path": ENTRY_FILE,
                "file_count": len(result.blobs),
            },
            suggested_type=ResourceType.SKILL,
            suggested_slug=f"skill:{skill_name}",
            suggested_display_name=skill_name,
            suggested_description=skill_desc,
        )
