"""Renderer ABC + shared markdown helpers for env docs."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from agentbox.core.workspace.env_doc.schema import EnvDocContent, Section, Visibility


@dataclass(frozen=True)
class ReferenceEntry:
    label: str
    detail: str = ""


@dataclass(frozen=True)
class RuntimeContext:
    """Resolved runtime data the renderer can splice into the references block."""

    skills: list[ReferenceEntry] = field(default_factory=list)
    folders: list[ReferenceEntry] = field(default_factory=list)


def _visible_for(section: Section, audience: Visibility) -> bool:
    if section.visibility == "hidden":
        return False
    if section.visibility == "both":
        return True
    return section.visibility == audience


def _render_commands_table(commands: list) -> str:
    if not commands:
        return ""
    lines = ["| Label | Command | Description |", "|---|---|---|"]
    for c in commands:
        lines.append(f"| {c.label} | `{c.command}` | {c.description} |")
    return "\n".join(lines)


def _render_bullets(items: list[str]) -> str:
    return "\n".join(f"- {x}" for x in items if x)


def _render_layout(layout: str | None) -> str:
    if not layout:
        return ""
    return f"```\n{layout.rstrip()}\n```"


def _render_references(content: EnvDocContent, ctx: RuntimeContext) -> str:
    refs = content.references
    parts: list[str] = []
    if refs.include_skills and ctx.skills:
        parts.append("**Skills available:**")
        parts.extend(
            f"- {s.label}" + (f" — {s.detail}" if s.detail else "") for s in ctx.skills
        )
    if refs.include_folders and ctx.folders:
        parts.append("**Folders:**")
        parts.extend(
            f"- {f.label}" + (f" — {f.detail}" if f.detail else "") for f in ctx.folders
        )
    if refs.custom_links:
        parts.append("**Links:**")
        parts.extend(f"- [{link.label}]({link.url})" for link in refs.custom_links)
    return "\n".join(parts)


def _render_body(
    content: EnvDocContent, ctx: RuntimeContext, audience: Visibility
) -> str:
    blocks: list[str] = []
    if content.project_name:
        blocks.append(f"# {content.project_name}")
    if content.overview:
        blocks.append(content.overview.strip())
    layout = _render_layout(content.working_directory_layout)
    if layout:
        blocks.append("## Working directory layout")
        blocks.append(layout)
    if content.conventions:
        blocks.append("## Conventions")
        blocks.append(_render_bullets(content.conventions))
    if content.commands:
        blocks.append("## Commands")
        blocks.append(_render_commands_table(content.commands))
    if content.verification:
        blocks.append("## Verification")
        blocks.append(_render_bullets(content.verification))
    for section in content.sections:
        if _visible_for(section, audience):
            blocks.append(f"## {section.title}")
            if section.body_markdown.strip():
                blocks.append(section.body_markdown.strip())
    refs = _render_references(content, ctx)
    if refs:
        blocks.append("## Resources available in this workspace")
        blocks.append(refs)
    return "\n\n".join(blocks).rstrip() + "\n"


class EnvDocRenderer(ABC):
    audience: Visibility

    @abstractmethod
    def render(self, content: EnvDocContent, ctx: RuntimeContext) -> str: ...
