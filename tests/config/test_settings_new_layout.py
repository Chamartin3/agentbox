"""Tests for the Plan-08 Settings layout (manifest-only host contract)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentbox.config import Settings, _optional_dir, load_settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_settings(
    manifest_path: Path,
    data_dir: Path | None = None,
    agents_dir: Path | None = None,
    prompts_dir: Path | None = None,
    skills_dir: Path | None = None,
    outputs_dir: Path | None = None,
) -> Settings:
    dd = data_dir or Path("/data")
    return Settings(
        manifest_path=manifest_path,
        data_dir=dd,
        db_path=dd / "agentbox.sqlite",
        port=8765,
        host="0.0.0.0",
        agents_dir=agents_dir,
        prompts_dir=prompts_dir,
        skills_dir=skills_dir,
        outputs_dir=outputs_dir,
        completion_webhook_url=None,
    )


# ---------------------------------------------------------------------------
# check_manifest
# ---------------------------------------------------------------------------


def test_check_manifest_raises_when_missing(tmp_path: Path) -> None:
    s = make_settings(tmp_path / "nonexistent.toml")
    with pytest.raises(RuntimeError, match="agentbox cannot start"):
        s.check_manifest()


def test_check_manifest_message_contains_env_var(tmp_path: Path) -> None:
    s = make_settings(tmp_path / "nonexistent.toml")
    with pytest.raises(RuntimeError, match="AGENTBOX_MANIFEST"):
        s.check_manifest()


def test_check_manifest_passes_when_present(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.toml"
    manifest.write_text('project = "test"\n')
    s = make_settings(manifest)
    s.check_manifest()  # should not raise


# ---------------------------------------------------------------------------
# Derived properties
# ---------------------------------------------------------------------------


def test_project_root_is_manifest_parent(tmp_path: Path) -> None:
    s = make_settings(tmp_path / "manifest.toml")
    assert s.project_root == tmp_path


def test_workspaces_root_derived_from_project_root(tmp_path: Path) -> None:
    s = make_settings(tmp_path / "manifest.toml")
    assert s.workspaces_root == tmp_path / "workspaces"


# ---------------------------------------------------------------------------
# Optional mounts — unset → None
# ---------------------------------------------------------------------------


def test_optional_dirs_default_none_when_devnull(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTBOX_AGENTS_DIR", "/dev/null")
    assert _optional_dir("AGENTBOX_AGENTS_DIR") is None


def test_optional_dirs_none_when_env_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENTBOX_AGENTS_DIR", raising=False)
    assert _optional_dir("AGENTBOX_AGENTS_DIR") is None


def test_optional_dirs_set_when_valid_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AGENTBOX_AGENTS_DIR", str(tmp_path / "agents.d"))
    result = _optional_dir("AGENTBOX_AGENTS_DIR")
    assert result == tmp_path / "agents.d"


# ---------------------------------------------------------------------------
# load_settings — env-var round-trips
# ---------------------------------------------------------------------------


def test_load_settings_manifest_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AGENTBOX_MANIFEST", str(tmp_path / "my.toml"))
    # Clear optional dir env vars so defaults don't create Path("/agentbox/...")
    for var in ("AGENTBOX_AGENTS_DIR", "AGENTBOX_PROMPTS_DIR", "AGENTBOX_SKILLS_DIR", "AGENTBOX_OUTPUTS_DIR"):
        monkeypatch.setenv(var, "/dev/null")
    s = load_settings()
    assert s.manifest_path == tmp_path / "my.toml"


def test_load_settings_all_optional_unset(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AGENTBOX_MANIFEST", str(tmp_path / "manifest.toml"))
    for var in ("AGENTBOX_AGENTS_DIR", "AGENTBOX_PROMPTS_DIR", "AGENTBOX_SKILLS_DIR", "AGENTBOX_OUTPUTS_DIR"):
        monkeypatch.setenv(var, "/dev/null")
    s = load_settings()
    assert s.agents_dir is None
    assert s.prompts_dir is None
    assert s.skills_dir is None
    assert s.outputs_dir is None


def test_load_settings_all_optional_set(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AGENTBOX_MANIFEST", str(tmp_path / "manifest.toml"))
    monkeypatch.setenv("AGENTBOX_AGENTS_DIR", str(tmp_path / "agents.d"))
    monkeypatch.setenv("AGENTBOX_PROMPTS_DIR", str(tmp_path / "prompts.d"))
    monkeypatch.setenv("AGENTBOX_SKILLS_DIR", str(tmp_path / "skills.d"))
    monkeypatch.setenv("AGENTBOX_OUTPUTS_DIR", str(tmp_path / "outputs"))
    s = load_settings()
    assert s.agents_dir == tmp_path / "agents.d"
    assert s.prompts_dir == tmp_path / "prompts.d"
    assert s.skills_dir == tmp_path / "skills.d"
    assert s.outputs_dir == tmp_path / "outputs"
