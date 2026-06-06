"""Tests for multi-root skill discovery in boot_import."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from agentbox.core.data import SessionStore
from agentbox.core.resources.boot_import import (
    import_one_skill,
    import_repo_resources,
    resolve_skill_roots,
)


@pytest.fixture
def store(tmp_path: Path) -> SessionStore:
    return SessionStore(tmp_path / "db.sqlite")


def _make_skill(root: Path, name: str, body: str = "skill body") -> Path:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: a {name} skill\n---\n\n{body}\n"
    )
    return d


def test_import_repo_resources_discovers_skills_across_roots(
    store: SessionStore, tmp_path: Path
) -> None:
    _make_skill(tmp_path / "apps" / "cvman" / "mcp" / "skills", "foo")
    _make_skill(tmp_path / "agentbox" / "skills", "bar")

    summary = import_repo_resources(store, tmp_path)
    assert summary["failed"] == 0
    assert summary["created"] >= 2

    foo = store.get_repo_resource_by_slug("skill:foo")
    bar = store.get_repo_resource_by_slug("skill:bar")
    assert foo is not None and foo["type"] == "skill"
    assert bar is not None and bar["type"] == "skill"


def test_duplicate_skill_names_log_warning(
    store: SessionStore, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _make_skill(tmp_path / "apps" / "cvman" / "mcp" / "skills", "dup", body="A")
    _make_skill(tmp_path / "agentbox" / "skills", "dup", body="B")

    with caplog.at_level(logging.WARNING, logger="agentbox.core.resources.boot_import"):
        import_repo_resources(store, tmp_path)

    msgs = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("duplicate skill" in m and "dup" in m for m in msgs), msgs

    dup = store.get_repo_resource_by_slug("skill:dup")
    assert dup is not None and dup["type"] == "skill"


def test_resolve_skill_roots_respects_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    extra = tmp_path / "custom" / "skills"
    extra.mkdir(parents=True)
    monkeypatch.setenv("AGENTBOX_EXTRA_SKILL_ROOTS", str(extra))
    roots = resolve_skill_roots(tmp_path)
    assert extra in roots or extra.resolve() in [r.resolve() for r in roots]


def test_resolve_skill_roots_skips_vendor_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bad = tmp_path / ".venv" / "skills"
    bad.mkdir(parents=True)
    monkeypatch.setenv("AGENTBOX_EXTRA_SKILL_ROOTS", str(bad))
    roots = resolve_skill_roots(tmp_path)
    assert bad not in roots


def test_import_one_skill_idempotent(store: SessionStore, tmp_path: Path) -> None:
    skill_dir = _make_skill(tmp_path / "skills", "solo")
    action1, slug = import_one_skill(store, skill_dir, tmp_path)
    assert action1 == "created"
    assert slug == "skill:solo"
    action2, _ = import_one_skill(store, skill_dir, tmp_path)
    assert action2 == "skipped"
