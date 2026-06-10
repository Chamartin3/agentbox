"""Engine-agnostic output types for the config generator."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Role(str, Enum):
    """Role of an output item — determines its file path via recipe layout."""

    context = "context"
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


@dataclass
class RenderedDir:
    """Result of a render operation."""

    target_dir: Path
    written_paths: list[Path] = field(default_factory=list)
