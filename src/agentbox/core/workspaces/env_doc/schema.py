"""Pydantic schema for the structured environment-instruction doc (Plan 04)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Visibility = Literal["both", "claude_only", "agents_only", "hidden"]


class Command(BaseModel):
    label: str
    command: str
    description: str = ""


class Section(BaseModel):
    id: str
    title: str
    body_markdown: str = ""
    visibility: Visibility = "both"


class CustomLink(BaseModel):
    label: str
    url: str


class References(BaseModel):
    include_skills: bool = True
    include_folders: bool = True
    custom_links: list[CustomLink] = Field(default_factory=list)


class EnvDocContent(BaseModel):
    project_name: str = ""
    overview: str = ""
    working_directory_layout: str | None = None
    conventions: list[str] = Field(default_factory=list)
    commands: list[Command] = Field(default_factory=list)
    verification: list[str] | None = None
    sections: list[Section] = Field(default_factory=list)
    references: References = Field(default_factory=References)
