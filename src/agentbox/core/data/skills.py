"""Skill-pack shape.

The pure value type describing a discovered skill pack. Discovery logic
(``discover_skills`` etc.) lives in ``core.resources.skills``; the shape
lives here so ``core.data`` boundary types (``RenderedConfig``) can name
it without importing the resources domain.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class SkillPack:
    name: str
    path: Path
    content: str
