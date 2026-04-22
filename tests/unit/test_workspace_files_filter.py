"""Generated configs, permissions, and skill packs are hidden from the user file list.

The Files panel in the workspace UI should only show files the user authored.
Generated artifacts (.agentbox/, .claude/, .opencode/) and capabilities.json
each have their own UI section, so duplicating them in the list adds noise.
"""

from __future__ import annotations

from pathlib import Path

from agentbox.api.routes.workspaces import _is_user_file


def test_user_file_at_root_is_kept() -> None:
    assert _is_user_file("README.md")
    assert _is_user_file("notes/research.md")
    assert _is_user_file("scratch.txt")


def test_generated_configs_are_hidden() -> None:
    assert not _is_user_file(".agentbox/generated/claude_settings.json")
    assert not _is_user_file(".agentbox/generated/claude_agents.json")
    assert not _is_user_file(".agentbox/generated/opencode.json")


def test_capabilities_and_runtime_dirs_are_hidden() -> None:
    assert not _is_user_file("permissions/capabilities.json")
    assert not _is_user_file(".claude/skills/foo/SKILL.md")
    assert not _is_user_file(".opencode/skills/foo/SKILL.md")


def test_skill_packs_are_hidden() -> None:
    # Skill packs live under skills/ and have their own UI section.
    assert not _is_user_file("skills/draft_review/SKILL.md")


def test_filter_against_real_workspace_layout(tmp_path: Path) -> None:
    """Sanity check the filter against a realistic directory layout."""
    (tmp_path / "README.md").write_text("hi")
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "x.md").write_text("x")
    (tmp_path / ".agentbox" / "generated").mkdir(parents=True)
    (tmp_path / ".agentbox" / "generated" / "claude_settings.json").write_text("{}")
    (tmp_path / "permissions").mkdir()
    (tmp_path / "permissions" / "capabilities.json").write_text("{}")
    (tmp_path / "skills" / "review").mkdir(parents=True)
    (tmp_path / "skills" / "review" / "SKILL.md").write_text("# review")

    kept = [
        str(p.relative_to(tmp_path))
        for p in sorted(tmp_path.rglob("*"))
        if p.is_file() and _is_user_file(str(p.relative_to(tmp_path)))
    ]
    assert kept == ["README.md", "notes/x.md"]
